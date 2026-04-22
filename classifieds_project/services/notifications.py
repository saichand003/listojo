from __future__ import annotations

from django.conf import settings
from django.core.mail import send_mail


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
