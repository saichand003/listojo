"""
Login step-up OTP ("Confirm it's you") for password logins.

Flow (all state held in the session, since the user isn't logged in yet):
  1. start_email_otp(request, user)  → generates a 6-digit code, emails it,
     stores a salted hash + expiry in the session, returns nothing.
  2. switch_to_sms(request, user)    → sends the code via Twilio Verify to the
     user's verified phone (Twilio owns the code in this mode).
  3. check_otp(request, code)        → validates against email hash OR Twilio,
     returns the pending user on success, else None.

Email is primary; SMS (Twilio Verify) is the "Try another way" fallback.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
import threading
import time

from django.conf import settings
from django.core import signing
from django.core.mail import send_mail

logger = logging.getLogger(__name__)


def _send_email_async(subject: str, body: str, to: str) -> None:
    """Fire-and-forget email send so a slow SMTP server can't block the request."""
    def _run():
        try:
            send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [to], fail_silently=True)
        except Exception:  # noqa: BLE001
            logger.exception('async OTP email send failed to %s', to)
    threading.Thread(target=_run, daemon=True).start()

CODE_TTL = 10 * 60      # seconds a code stays valid
MAX_ATTEMPTS = 5
RESEND_COOLDOWN = 30    # seconds between resends

_S = 'pw_otp'           # session key prefix

# ── Trusted-device ("remember this device for 30 days") ──────────────────────
TRUST_COOKIE = 'lj_trusted_device'
TRUST_MAX_AGE = 30 * 24 * 60 * 60   # 30 days


def _device_salt(user) -> str:
    # Binding to a fragment of the password hash means changing the password
    # (or a reset) automatically invalidates all trusted devices.
    return 'lj-device-' + (user.password or '')[-16:]


def make_trust_token(user) -> str:
    return signing.dumps({'uid': user.pk}, salt=_device_salt(user))


def is_trusted_device(request, user) -> bool:
    token = request.COOKIES.get(TRUST_COOKIE)
    if not token:
        return False
    try:
        data = signing.loads(token, salt=_device_salt(user), max_age=TRUST_MAX_AGE)
    except signing.BadSignature:
        return False
    return data.get('uid') == user.pk


def set_trusted_cookie(response, user):
    response.set_cookie(
        TRUST_COOKIE, make_trust_token(user),
        max_age=TRUST_MAX_AGE,
        httponly=True,
        secure=not settings.DEBUG,
        samesite='Lax',
    )
    return response


def _hash(code: str) -> str:
    key = (settings.SECRET_KEY or 'x').encode()
    return hmac.new(key, code.encode(), hashlib.sha256).hexdigest()


def mask_email(email: str) -> str:
    if not email or '@' not in email:
        return email or ''
    name, domain = email.split('@', 1)
    if len(name) <= 2:
        shown = name[0]
    else:
        shown = name[0] + '***' + name[-1]
    return f'{shown}@{domain}'


def mask_phone(phone: str) -> str:
    if not phone:
        return ''
    return '+1 ***-***-' + phone[-4:]


def pending_user_id(request) -> int | None:
    return request.session.get(f'{_S}_uid')


def begin(request, user, *, remember: bool, next_url: str) -> None:
    """Record who is mid-login and their post-verify intent."""
    request.session[f'{_S}_uid'] = user.pk
    request.session[f'{_S}_remember'] = bool(remember)
    request.session[f'{_S}_next'] = next_url or ''


def pop_intent(request) -> tuple[bool, str]:
    remember = bool(request.session.pop(f'{_S}_remember', False))
    next_url = request.session.pop(f'{_S}_next', '') or ''
    return remember, next_url


def clear(request) -> None:
    for k in ('uid', 'remember', 'next', 'hash', 'exp', 'attempts', 'channel', 'last_sent'):
        request.session.pop(f'{_S}_{k}', None)


def _can_resend(request) -> bool:
    last = request.session.get(f'{_S}_last_sent', 0)
    return (time.time() - last) >= RESEND_COOLDOWN


def start_email_otp(request, user) -> bool:
    """Generate + email a fresh 6-digit code. Returns False if on cooldown."""
    if not _can_resend(request):
        return False
    code = f'{secrets.randbelow(1_000_000):06d}'
    request.session[f'{_S}_hash'] = _hash(code)
    request.session[f'{_S}_exp'] = time.time() + CODE_TTL
    request.session[f'{_S}_attempts'] = 0
    request.session[f'{_S}_channel'] = 'email'
    request.session[f'{_S}_last_sent'] = time.time()

    if user.email:
        _send_email_async(
            'Your Listojo verification code',
            (
                f'Hi {user.get_full_name() or user.username},\n\n'
                f'Your verification code is: {code}\n\n'
                f'It expires in 10 minutes. If you didn’t try to sign in, ignore this email.'
            ),
            user.email,
        )
    return True


def start_sms_otp(request, user) -> bool:
    """Send the code via Twilio Verify to the user's verified phone."""
    profile = getattr(user, 'profile', None)
    if not profile or not (profile.phone_verified and profile.phone):
        return False
    from accounts.services.twilio_service import start_verification
    if not start_verification(profile.phone):
        return False
    request.session[f'{_S}_channel'] = 'sms'
    request.session[f'{_S}_exp'] = time.time() + CODE_TTL
    request.session[f'{_S}_attempts'] = 0
    request.session[f'{_S}_last_sent'] = time.time()
    return True


def channel(request) -> str:
    return request.session.get(f'{_S}_channel', 'email')


def check_otp(request, user, code: str) -> bool:
    """Validate the entered code for the current channel."""
    code = (code or '').strip()
    if not code:
        return False

    exp = request.session.get(f'{_S}_exp', 0)
    if time.time() > exp:
        return False

    attempts = request.session.get(f'{_S}_attempts', 0)
    if attempts >= MAX_ATTEMPTS:
        return False
    request.session[f'{_S}_attempts'] = attempts + 1

    if channel(request) == 'sms':
        profile = getattr(user, 'profile', None)
        if not profile or not profile.phone:
            return False
        from accounts.services.twilio_service import check_verification
        return check_verification(profile.phone, code)

    # email channel — compare against stored hash
    stored = request.session.get(f'{_S}_hash', '')
    return bool(stored) and hmac.compare_digest(stored, _hash(code))
