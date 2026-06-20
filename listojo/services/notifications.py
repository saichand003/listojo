from __future__ import annotations

import logging

from django.conf import settings
from django.core.mail import send_mail

logger = logging.getLogger(__name__)


def _get_profile(user):
    """Return the user's profile, tolerating users created before profiles existed."""
    profile = getattr(user, 'profile', None)
    if profile is None:
        try:
            from accounts.models import UserProfile
            profile, _ = UserProfile.objects.get_or_create(user=user)
        except Exception:
            return None
    return profile


def notify_user(user, *, subject: str, email_body: str, sms_body: str | None = None) -> dict:
    """
    Send a notification across the channels the user has opted into.

    - Email when the profile allows it (notify_email + has email).
    - SMS when the profile allows it (notify_sms + verified phone) and sms_body given.

    Returns {'email': bool, 'sms': bool} indicating what was sent.
    """
    sent = {'email': False, 'sms': False}
    profile = _get_profile(user)
    if profile is None:
        return sent

    if profile.can_email:
        try:
            send_mail(
                subject=subject,
                message=email_body,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
                fail_silently=True,
            )
            sent['email'] = True
        except Exception:
            logger.exception('notify_user: email failed for %s', user)

    if sms_body and profile.can_sms:
        try:
            from accounts.services.twilio_service import send_sms
            sent['sms'] = send_sms(profile.phone, sms_body)
        except Exception:
            logger.exception('notify_user: sms failed for %s', user)

    return sent


def send_listing_inquiry_email(listing, inquiry) -> None:
    """Send an inquiry notification to a listing owner when email is available."""
    if not listing.owner.email:
        return
    send_mail(
        subject=f'New inquiry for "{listing.title}"',
        message=(
            f'Hi {listing.owner.username},\n\n'
            f'{inquiry.name} sent an inquiry about your listing "{listing.title}".\n\n'
            f'Message:\n{inquiry.message}\n\n'
            f'Reply to: {inquiry.email}'
            + (f'\nPhone: {inquiry.phone}' if inquiry.phone else '')
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[listing.owner.email],
        fail_silently=True,
    )
