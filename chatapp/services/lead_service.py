from __future__ import annotations

from portal.services.lead_service import create_or_update_lead


def maybe_create_chat_lead(sender, listing):
    """Create or update a lead on the first visitor chat against a listing."""
    assigned = listing.owner if listing.owner.is_staff else None
    return create_or_update_lead(
        name=sender.get_full_name().strip() or sender.username,
        email=sender.email,
        source='chat',
        listing=listing,
        assigned_agent=assigned,
        city=listing.city,
        property_type=listing.category,
    )
