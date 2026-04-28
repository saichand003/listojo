from __future__ import annotations

from django.conf import settings
from django.core.cache import cache
from django.core.mail import send_mail

from portal.services.lead_service import create_or_update_lead
from portal.services.routing import least_loaded_agent

from .event_tracker import log_community_event


def handle_tour_request(request, community, inquiry: dict) -> tuple[bool, str | None]:
    """
    Process a validated tour inquiry for a community.
    Returns (success, error_message). On success error_message is None.
    """
    rate_key = (
        f'community-tour:{community.pk}:'
        f'{request.session.session_key or request.META.get("REMOTE_ADDR", "")}'
    )
    if cache.get(rate_key):
        return False, 'Please wait a moment before sending another tour request.'

    recipient = community.contact_email or community.owner.email
    if recipient:
        tour_type = inquiry.get('tour_type', '') or 'Not specified'
        phone_line = f'\nPhone: {inquiry["phone"]}' if inquiry.get('phone') else ''
        send_mail(
            subject=f'New community tour request for "{community.name}"',
            message=(
                f'Hi {community.owner.username},\n\n'
                f'{inquiry["name"]} requested a tour for "{community.name}".\n\n'
                f'Tour type: {tour_type}\n'
                f'Message:\n{inquiry["message"]}\n\n'
                f'Reply to: {inquiry["email"]}{phone_line}'
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[recipient],
            fail_silently=True,
        )

    create_or_update_lead(
        name=inquiry['name'],
        email=inquiry['email'],
        phone=inquiry.get('phone', ''),
        source='inquiry',
        community=community,
        assigned_agent=least_loaded_agent(),
        city=community.city,
        property_type=community.community_type or 'community',
        amenities=community.community_amenities,
    )
    cache.set(rate_key, True, 30)
    log_community_event(request, community, 'tour_request')
    return True, None
