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
    community=None,
    assigned_agent=None,
    city: str = '',
    property_type: str = '',
    bedrooms: int | None = None,
    max_budget: Decimal | None = None,
    amenities: str = '',
    move_in_date: date | None = None,
    priority: str = '',
    urgency: str = '',
    monthly_income: Decimal | None = None,
) -> Lead:
    lead = None

    if source == 'guided_search' and email:
        lead = (
            Lead.objects.filter(email=email, source='guided_search', assigned_agent__isnull=True)
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
            community=community,
            assigned_agent=assigned_agent,
        )
    else:
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
        if community and not lead.community:
            lead.community = community
            updated = True
        if updated:
            lead.save()

    LeadPreference.objects.update_or_create(
        lead=lead,
        defaults={k: v for k, v in {
            'city': city or (listing.city if listing else ''),
            'property_type': property_type or (listing.category if listing else ''),
            'bedrooms': bedrooms,
            'max_budget': max_budget,
            'amenities': amenities,
            'move_in_date': move_in_date,
            'priority': priority,
            'urgency': urgency,
            'monthly_income': monthly_income,
        }.items() if v not in (None, '', 0)}
    )
    return lead


def parse_budget(value) -> Decimal | None:
    if not value:
        return None
    try:
        return Decimal(str(value))
    except InvalidOperation:
        return None


def parse_move_in(value) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return None
