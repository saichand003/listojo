"""
Shortlist lifecycle service.

All shortlist creation, sending, and engagement tracking must go through
this module. Views must not instantiate Shortlist/ShortlistItem directly.
"""
from __future__ import annotations

from django.contrib.auth.models import User
from django.utils import timezone

from listings.services.matching import score_for_preference
from listings.services.visibility import active_listings
from portal.models import Lead, LeadPreference, Shortlist, ShortlistItem


def build_curated(lead: Lead, limit: int = 6) -> list[dict]:
    """
    Return up to `limit` listings auto-matched to the lead's preferences,
    sorted by match score descending.

    Each dict: {listing, match_pct, reasons, caveats}
    """
    preference = getattr(lead, 'preference', None)
    if not preference or not preference.city:
        return []

    already_shortlisted = {
        i.listing_id
        for sl in lead.shortlists.prefetch_related('items')
        for i in sl.items.all()
    }

    qs = active_listings().filter(city__icontains=preference.city).exclude(
        id__in=already_shortlisted
    )
    if preference.bedrooms:
        qs = qs.filter(bedrooms=preference.bedrooms)
    if preference.max_budget:
        qs = qs.filter(price__lte=float(preference.max_budget) * 1.1)

    results = []
    for listing in qs[:12]:
        result = score_for_preference(listing, preference)
        results.append({
            'listing':   listing,
            'match_pct': result.pct,
            'reasons':   result.reasons,
            'caveats':   result.caveats,
        })

    results.sort(key=lambda x: -x['match_pct'])
    return results[:limit]


def create_shortlist(lead: Lead, agent: User, listing_ids: list[int]) -> Shortlist | None:
    """
    Create a draft Shortlist for a lead from a list of listing PKs.
    Silently skips IDs that don't match active listings.
    Returns None if no valid listings were provided.
    """
    valid = list(active_listings().filter(pk__in=listing_ids))
    if not valid:
        return None

    sl = Shortlist.objects.create(lead=lead, agent=agent)
    for idx, listing in enumerate(valid):
        ShortlistItem.objects.create(shortlist=sl, listing=listing, order_index=idx)
    return sl


def send_shortlist(shortlist: Shortlist) -> None:
    """Mark a shortlist as sent and record the timestamp."""
    shortlist.status = 'sent'
    shortlist.sent_at = timezone.now()
    shortlist.save(update_fields=['status', 'sent_at'])


def create_and_send(lead: Lead, agent: User, listing_ids: list[int]) -> Shortlist | None:
    """Create a shortlist and immediately mark it sent. Returns None on failure."""
    sl = create_shortlist(lead, agent, listing_ids)
    if sl:
        send_shortlist(sl)
        lead.status = 'shortlist_sent'
        lead.save(update_fields=['status', 'updated_at'])
    return sl


def generate_conversion_tip(curated: list[dict], preference) -> str | None:
    """Generate a one-line agent tip from the top curated match."""
    if not curated:
        return None
    top = curated[0]
    listing = top['listing']
    tips = []
    if 'Under budget' in top['reasons'] and preference and preference.max_budget and listing.price:
        savings = int(float(preference.max_budget) - float(listing.price))
        tips.append(f"Lead with the ${savings:,}/mo savings vs their budget")
    if 'Pet friendly' in top['reasons']:
        tips.append("pet-friendly angle is a strong differentiator")
    if preference and preference.amenities:
        top_amenity = preference.amenities.split(',')[0].strip().title()
        if top_amenity and top_amenity.lower() not in ['under budget', 'pet friendly']:
            tips.append(f"{top_amenity} is a stated must-have — confirm it's available")
    if not tips:
        city = getattr(preference, 'city', None) or listing.city
        tips.append(f"{listing.city} area matches their target location")
    return f"{listing.title[:28]}… is your strongest lead — {tips[0]}."
