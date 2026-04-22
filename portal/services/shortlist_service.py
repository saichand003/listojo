from __future__ import annotations

from django.contrib.auth.models import User
from django.utils import timezone

from listings.services.matching import score_for_preference
from listings.services.visibility import active_listings
from portal.models import Lead, Shortlist, ShortlistItem


def build_curated(lead: Lead, limit: int = 6) -> list[dict]:
    preference = getattr(lead, 'preference', None)
    if not preference or not preference.city:
        return []

    already_shortlisted = {
        item.listing_id
        for shortlist in lead.shortlists.prefetch_related('items')
        for item in shortlist.items.all()
    }

    qs = active_listings().filter(city__icontains=preference.city).exclude(id__in=already_shortlisted)
    if preference.bedrooms:
        qs = qs.filter(bedrooms=preference.bedrooms)
    if preference.max_budget:
        qs = qs.filter(price__lte=float(preference.max_budget) * 1.1)

    curated = []
    for listing in qs[:12]:
        result = score_for_preference(listing, preference)
        curated.append({
            'listing': listing,
            'match_pct': result.pct,
            'reasons': result.reasons,
            'caveats': result.caveats,
        })

    curated.sort(key=lambda item: -item['match_pct'])
    return curated[:limit]


def build_manual_listing_pool(lead: Lead, curated_ids: set[int], limit: int = 30) -> list:
    preference = getattr(lead, 'preference', None)
    city = None
    if preference and preference.city:
        city = preference.city
    elif lead.listing:
        city = lead.listing.city
    if not city:
        return []

    already_shortlisted = {
        item.listing_id
        for shortlist in lead.shortlists.prefetch_related('items')
        for item in shortlist.items.all()
    }
    exclude_ids = already_shortlisted | set(curated_ids)
    return list(
        active_listings()
        .filter(city__icontains=city)
        .exclude(id__in=exclude_ids)
        .order_by('-featured', '-created_at')[:limit]
    )


def create_shortlist(lead: Lead, agent: User, listing_ids: list[int]) -> Shortlist | None:
    valid = list(active_listings().filter(pk__in=listing_ids))
    if not valid:
        return None

    shortlist = Shortlist.objects.create(lead=lead, agent=agent)
    for idx, listing in enumerate(valid):
        ShortlistItem.objects.create(shortlist=shortlist, listing=listing, order_index=idx)
    return shortlist


def send_shortlist(shortlist: Shortlist) -> None:
    shortlist.status = 'sent'
    shortlist.sent_at = timezone.now()
    shortlist.save(update_fields=['status', 'sent_at', 'updated_at'])


def create_and_send(lead: Lead, agent: User, listing_ids: list[int]) -> Shortlist | None:
    shortlist = create_shortlist(lead, agent, listing_ids)
    if shortlist:
        send_shortlist(shortlist)
        lead.status = 'shortlist_sent'
        lead.save(update_fields=['status', 'updated_at'])
    return shortlist


def generate_conversion_tip(curated: list[dict], preference) -> str | None:
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
        tips.append(f"{listing.city} area matches their target location")
    return f"{listing.title[:28]}… is your strongest lead — {tips[0]}."
