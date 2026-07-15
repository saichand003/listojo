"""
Lightweight signup abuse controls:
  • rate_limit()      — per-IP counter via the shared DB cache
  • verify_turnstile()— Cloudflare Turnstile CAPTCHA check (fail-open if unset)
  • client_ip()       — real client IP behind Railway's proxy
"""
from __future__ import annotations

import logging

import requests
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

_TURNSTILE_VERIFY = 'https://challenges.cloudflare.com/turnstile/v0/siteverify'


def client_ip(request) -> str:
    xff = request.META.get('HTTP_X_FORWARDED_FOR', '')
    if xff:
        return xff.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', '') or 'unknown'


def rate_limit(request, *, key: str, limit: int, window: int) -> bool:
    """
    Return True if the request is allowed, False if the per-IP limit is exceeded.
    `limit` requests are permitted per `window` seconds.
    """
    ip = client_ip(request)
    cache_key = f'rl:{key}:{ip}'
    try:
        count = cache.get_or_set(cache_key, 0, window)
        if count >= limit:
            return False
        cache.incr(cache_key)
    except Exception:  # noqa: BLE001 — never let the limiter break the request
        logger.exception('rate_limit cache error for %s', cache_key)
        return True
    return True


def turnstile_enabled() -> bool:
    return bool(getattr(settings, 'TURNSTILE_SITE_KEY', '') and getattr(settings, 'TURNSTILE_SECRET_KEY', ''))


# ── Adaptive login protection ─────────────────────────────────────────────────
LOGIN_CAPTCHA_THRESHOLD = 3          # failed attempts before CAPTCHA is required
_LOGIN_FAIL_WINDOW = 15 * 60         # failures decay after 15 min


def _login_fail_key(request) -> str:
    return f'loginfail:{client_ip(request)}'


def login_failures(request) -> int:
    return cache.get(_login_fail_key(request), 0)


def record_login_failure(request) -> int:
    key = _login_fail_key(request)
    try:
        count = cache.get_or_set(key, 0, _LOGIN_FAIL_WINDOW)
        cache.incr(key)
        return count + 1
    except Exception:  # noqa: BLE001
        logger.exception('record_login_failure cache error')
        return 0


def clear_login_failures(request) -> None:
    try:
        cache.delete(_login_fail_key(request))
    except Exception:  # noqa: BLE001
        pass


def login_captcha_required(request) -> bool:
    """CAPTCHA kicks in only after repeated failures (and only if configured)."""
    return turnstile_enabled() and login_failures(request) >= LOGIN_CAPTCHA_THRESHOLD


def verify_turnstile(request) -> bool:
    """
    Verify the Turnstile token from the form. Fail-open (True) when Turnstile
    isn't configured, so signup keeps working until keys are added.
    """
    if not turnstile_enabled():
        return True
    token = request.POST.get('cf-turnstile-response', '')
    if not token:
        return False
    try:
        resp = requests.post(
            _TURNSTILE_VERIFY,
            data={
                'secret': settings.TURNSTILE_SECRET_KEY,
                'response': token,
                'remoteip': client_ip(request),
            },
            timeout=6,
        )
        return bool(resp.json().get('success'))
    except (requests.RequestException, ValueError):
        logger.exception('Turnstile verification request failed')
        return False
