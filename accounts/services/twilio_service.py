"""
Thin wrapper around Twilio for phone verification (Verify) and SMS.

Every function degrades gracefully when credentials are missing — it logs and
returns a falsy/neutral result instead of raising, so the app keeps working
without Twilio configured (e.g. local dev).

Env / settings required for live use:
    TWILIO_ACCOUNT_SID
    TWILIO_AUTH_TOKEN
    TWILIO_VERIFY_SERVICE_SID   # phone verification (OTP)
    TWILIO_SMS_FROM             # sender number for notifications
"""
from __future__ import annotations

import logging

from django.conf import settings

logger = logging.getLogger(__name__)


def _client():
    """Return a configured Twilio REST client, or None if not configured."""
    sid = getattr(settings, 'TWILIO_ACCOUNT_SID', '')
    token = getattr(settings, 'TWILIO_AUTH_TOKEN', '')
    if not (sid and token):
        return None
    try:
        from twilio.rest import Client
    except ImportError:
        logger.warning('twilio package not installed — SMS/verify disabled')
        return None
    try:
        return Client(sid, token)
    except Exception:
        logger.exception('Failed to build Twilio client')
        return None


# ── Phone verification (Twilio Verify) ────────────────────────────────────────

def start_verification(phone: str) -> bool:
    """Send an OTP code to `phone` (E.164). Returns True if the send was queued."""
    client = _client()
    service_sid = getattr(settings, 'TWILIO_VERIFY_SERVICE_SID', '')
    if not client or not service_sid:
        logger.info('start_verification skipped (Twilio Verify not configured) for %s', phone)
        return False
    try:
        client.verify.v2.services(service_sid).verifications.create(to=phone, channel='sms')
        return True
    except Exception:
        logger.exception('start_verification failed for %s', phone)
        return False


def check_verification(phone: str, code: str) -> bool:
    """Check the OTP `code` for `phone`. Returns True only on 'approved'."""
    client = _client()
    service_sid = getattr(settings, 'TWILIO_VERIFY_SERVICE_SID', '')
    if not client or not service_sid:
        return False
    try:
        result = client.verify.v2.services(service_sid).verification_checks.create(
            to=phone, code=code,
        )
        return result.status == 'approved'
    except Exception:
        logger.exception('check_verification failed for %s', phone)
        return False


# ── SMS notifications (Twilio Programmable SMS) ───────────────────────────────

def send_sms(to: str, body: str) -> bool:
    """Send an SMS. Returns True if queued. No-op (False) when not configured."""
    client = _client()
    from_number = getattr(settings, 'TWILIO_SMS_FROM', '')
    if not client or not from_number:
        logger.info('send_sms skipped (Twilio SMS not configured) to %s', to)
        return False
    if not to:
        return False
    try:
        client.messages.create(to=to, from_=from_number, body=body)
        return True
    except Exception:
        logger.exception('send_sms failed to %s', to)
        return False
