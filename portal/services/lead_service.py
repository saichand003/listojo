"""
Lead creation and preference management service.

All lead creation — from inquiries, guided search, and chat — must go through
this module. Views and signal handlers must not create Lead objects directly.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation

from portal.models import Lead, LeadPreference


def create_or_update_lead(
    *,
    name: str,
    email: str,
    phone: str = '',
    source: str,
    listing=None,
    assigned_agent=None,
    city: str = '',
    property_type: str = '',
    bedrooms: int | None = None,
    max_budget: Decimal | None = None,
    amenities: str = '',
    move_in_date: date | None = None,
) -> Lead:
    """
    Create a new lead and its preference, or update an existing unassigned lead
    for the same email + source combination.

    Rules:
    - Inquiry leads (source='inquiry') are always new records per listing.
    - Guided-search leads (source='guided_search') dedup on email — update
      the most recent unassigned lead if one exists.
    - Chat leads (source='chat') dedup on email + listing.
    - Manual leads are always new.
    """
    lead = None

    if source == 'guided_search' and email:
        lead = (
            Lead.objects.filter(
                email=email, source='guided_search', assigned_agent__isnull=True
            )
            .order_by('-created_at')
            .first()
        )

    elif source == 'chat' and email and listing:
        lead = Lead.objects.filter(email=email, listing=listing).first()

    if lead is None:
        lead = Lead.objects.create(
            name=name,
            email=email,
            phone=phone,
            source=source,
            listing=listing,
            assigned_agent=assigned_agent,
        )
    else:
        # Update mutable fields on existing lead
        updated = False
        if name and lead.name in ('', 'Guest'):
            lead.name = name
            updated = True
        if phone and not lead.phone:
            lead.phone = phone
            updated = True
        if assigned_agent and not lead.assigned_agent:
            lead.assigned_agent = assigned_agent
            updated = True
        if updated:
            lead.save()

    _upsert_preference(
        lead,
        city=city or (listing.city if listing else ''),
        property_type=property_type or (listing.category if listing else ''),
        bedrooms=bedrooms,
        max_budget=max_budget,
        amenities=amenities,
        move_in_date=move_in_date,
    )

    return lead


def _upsert_preference(lead: Lead, **kwargs) -> LeadPreference:
    """Create or update the LeadPreference for a lead, ignoring empty values."""
    defaults = {k: v for k, v in kwargs.items() if v not in (None, '', 0)}
    pref, _ = LeadPreference.objects.update_or_create(lead=lead, defaults=defaults)
    return pref


def parse_budget(value) -> Decimal | None:
    """Safely parse a budget string/number to Decimal."""
    if not value:
        return None
    try:
        return Decimal(str(value))
    except InvalidOperation:
        return None


def parse_move_in(value) -> date | None:
    """Safely parse an ISO date string to date."""
    if not value:
        return None
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return None
