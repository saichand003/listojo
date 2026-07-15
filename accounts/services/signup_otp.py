"""
Email verification at signup.

To stop fake/bot signups, no User row is created until the email is proven:
the pending signup (username, email, password) is held in the server-side
session, a code is emailed, and the account is only created after it's
confirmed. Reuses the email/code primitives from login_otp.
"""
from __future__ import annotations

import hmac
import secrets
import time

from accounts.services.login_otp import (
    CODE_TTL, MAX_ATTEMPTS, RESEND_COOLDOWN, _hash, _send_email_async,
)

_S = 'signup_otp'


def pending(request) -> dict | None:
    return request.session.get(f'{_S}_data')


def clear(request) -> None:
    for k in ('data', 'hash', 'exp', 'attempts', 'last_sent'):
        request.session.pop(f'{_S}_{k}', None)


def _can_resend(request) -> bool:
    return (time.time() - request.session.get(f'{_S}_last_sent', 0)) >= RESEND_COOLDOWN


def begin(request, *, username: str, email: str, password: str,
          first_name: str = '', last_name: str = '') -> None:
    """Store the pending signup and email a verification code."""
    request.session[f'{_S}_data'] = {
        'username': username, 'email': email, 'password': password,
        'first_name': first_name, 'last_name': last_name,
    }
    _send_code(request, email, force=True)


def resend(request) -> bool:
    data = pending(request)
    if not data:
        return False
    return _send_code(request, data['email'], force=False)


def _send_code(request, email: str, *, force: bool) -> bool:
    if not force and not _can_resend(request):
        return False
    code = f'{secrets.randbelow(1_000_000):06d}'
    request.session[f'{_S}_hash'] = _hash(code)
    request.session[f'{_S}_exp'] = time.time() + CODE_TTL
    request.session[f'{_S}_attempts'] = 0
    request.session[f'{_S}_last_sent'] = time.time()
    _send_email_async(
        'Verify your email for Listojo',
        (
            'Welcome to Listojo!\n\n'
            f'Your verification code is: {code}\n\n'
            'Enter it to finish creating your account. It expires in 10 minutes.'
        ),
        email,
    )
    return True


def check(request, code: str) -> bool:
    code = (code or '').strip()
    if not code or not pending(request):
        return False
    if time.time() > request.session.get(f'{_S}_exp', 0):
        return False
    attempts = request.session.get(f'{_S}_attempts', 0)
    if attempts >= MAX_ATTEMPTS:
        return False
    request.session[f'{_S}_attempts'] = attempts + 1
    stored = request.session.get(f'{_S}_hash', '')
    return bool(stored) and hmac.compare_digest(stored, _hash(code))


def complete(request):
    """Create the verified user from the pending signup. Returns the User or None."""
    from django.contrib.auth.models import User
    data = pending(request)
    if not data:
        return None
    # Guard against a race where the username/email was taken meanwhile.
    if User.objects.filter(username=data['username']).exists():
        return None
    user = User.objects.create_user(
        username=data['username'], email=data['email'], password=data['password'],
        first_name=data.get('first_name', ''), last_name=data.get('last_name', ''),
    )
    clear(request)
    return user
