from __future__ import annotations

from datetime import date
from typing import NamedTuple

from django.utils import timezone


class MatchResult(NamedTuple):
    pct: int
    reasons: list[str]
    caveats: list[str]
    tag_hits: int


_TAG_RELATED: dict[str, list[str]] = {
    'garage': ['parking', 'covered parking', 'carport'],
    'lake': ['waterway', 'water view', 'canal', 'pond', 'pool'],
    'pool': ['gym', 'amenities', 'community pool'],
    'gym': ['fitness', 'workout', 'exercise'],
    'pet friendly': ['pet-friendly', 'pets allowed', 'dogs ok'],
    'furnished': ['fully furnished', 'semi-furnished'],
    'balcony': ['patio', 'terrace', 'deck', 'outdoor'],
    'gated': ['secured', 'secure', 'fenced'],
    'schools': ['near schools', 'good schools', 'school district'],
}

_TAG_LABELS: dict[str, str] = {
    'pet friendly': 'Pet friendly',
    'washer dryer': 'W/D in unit',
    'washer/dryer': 'W/D in unit',
    'parking': 'Parking',
    'central ac': 'Central AC',
    'gym': 'Gym',
    'pool': 'Pool',
    'furnished': 'Furnished',
    'bills included': 'Bills included',
    'gated': 'Gated',
    'balcony': 'Balcony',
    'high-speed internet': 'High-speed internet',
}


def score_listing(
    listing,
    *,
    max_price: float | None = None,
    requested_tags: list[str] | None = None,
    avail_date: date | None = None,
    accommodation_type: str = '',
    property_type: str = '',
    bedrooms: int | None = None,
) -> MatchResult:
    """Shared listing scoring for consumer search and agent matching."""
    pts, max_pts = 0, 0
    reasons: list[str] = []
    caveats: list[str] = []
    tag_hits = 0
    tags_lower = (listing.tags or '').lower()

    if max_price and max_price > 0:
        max_pts += 40
        if listing.price:
            price = float(listing.price)
            effective = price - (150 if listing.bills_included else 0)
            headroom = float(max_price) - effective
            if headroom >= 0:
                ratio = headroom / float(max_price)
                pts += 30 + min(10, int(ratio * 20))
                if listing.bills_included:
                    reasons.append(f"Bills included (effective ~${int(effective):,}/mo)")
                elif headroom >= 100:
                    reasons.append(f"${int(headroom):,} under budget")
                else:
                    reasons.append("Within budget")
            elif headroom >= -float(max_price) * 0.10:
                pts += 12
                caveats.append("Slightly over budget")
            else:
                caveats.append("Over budget")
        else:
            pts += 20

    if bedrooms and listing.bedrooms:
        max_pts += 10
        if listing.bedrooms == bedrooms:
            pts += 10
            reasons.append(f"{listing.bedrooms} bed match")

    if accommodation_type:
        max_pts += 15
        if listing.accommodation_type == accommodation_type:
            pts += 15
            reasons.append('Whole place' if accommodation_type == 'whole' else 'Single room')

    if property_type:
        max_pts += 10
        if listing.property_type == property_type:
            pts += 10
            reasons.append(listing.get_property_type_display())

    if requested_tags:
        for tag in requested_tags:
            max_pts += 15
            tag_l = tag.lower().strip()
            if tag_l in tags_lower:
                pts += 15
                tag_hits += 1
                reasons.append(_TAG_LABELS.get(tag_l, tag.title()))
            else:
                close = _TAG_RELATED.get(tag_l, [])
                if any(r in tags_lower for r in close):
                    pts += 5
                    reasons.append(f"Similar to {tag}")

    if avail_date:
        max_pts += 10
        if not listing.available_from or listing.available_from <= avail_date:
            pts += 10
            reasons.append("Available now" if not listing.available_from else "Meets move-in date")

    age_days = (timezone.now() - listing.created_at).days
    if age_days <= 3:
        pts += 5
        max_pts += 5
        reasons.append("Just listed" if age_days == 0 else f"Listed {age_days}d ago")

    if 'no deposit' in tags_lower or 'no-deposit' in tags_lower:
        pts += 3
        max_pts += 3
        reasons.append("No deposit")
    if listing.featured:
        pts += 2
        max_pts += 2

    if max_pts == 0:
        return MatchResult(70, reasons[:5], caveats[:2], tag_hits)

    pct = int(round(pts / max_pts * 100))
    return MatchResult(min(100, max(0, pct)), reasons[:5], caveats[:2], tag_hits)


def score_for_preference(listing, preference) -> MatchResult:
    tags = [t.strip() for t in preference.amenities.split(',') if t.strip()] if preference.amenities else []
    base = score_listing(
        listing,
        max_price=float(preference.max_budget) if preference.max_budget else None,
        requested_tags=tags,
        avail_date=preference.move_in_date,
        property_type=preference.property_type or '',
        bedrooms=preference.bedrooms,
    )

    # Apply priority boost: nudge the score toward what the user said matters most
    priority = getattr(preference, 'priority', '')
    if priority and listing.price and preference.max_budget:
        price = float(listing.price)
        budget = float(preference.max_budget)
        if priority == 'price' and price <= budget:
            boosted = min(100, base.pct + 8)
            return MatchResult(boosted, base.reasons, base.caveats, base.tag_hits)
        if priority == 'features' and base.tag_hits >= 2:
            boosted = min(100, base.pct + 6)
            return MatchResult(boosted, base.reasons, base.caveats, base.tag_hits)

    return base


def explain_match(
    listing,
    reasons: list[str],
    *,
    max_price: float | None = None,
    quality_tags: list[str] | None = None,
    accommodation_type: str = '',
    property_type: str = '',
) -> str | None:
    parts: list[str] = []
    quality_tags = quality_tags or []

    accom = listing.get_accommodation_type_display() if listing.accommodation_type else ''
    prop = listing.get_property_type_display() if listing.property_type else ''
    if property_type and listing.property_type == property_type and prop:
        parts.append(f"it's exactly the {prop.lower()} you're looking for")
    elif accommodation_type and listing.accommodation_type == accommodation_type:
        label = 'whole place' if accommodation_type == 'whole' else 'private room'
        parts.append(f"it's a {label}{(' — ' + prop.lower()) if prop else ''}")

    if listing.price and max_price:
        price = float(listing.price)
        budget = float(max_price)
        headroom = int(budget - price)
        if listing.bills_included:
            effective = int(price - 150)
            parts.append(
                f"bills are included — effective cost is ~${effective:,}/mo, saving you ${int(budget - effective):,} vs your budget"
            )
        elif headroom >= 500:
            parts.append(f"at ${int(price):,}/mo it's ${headroom:,} under your ${int(budget):,} budget — gives you room to save")
        elif headroom >= 100:
            parts.append(f"priced at ${int(price):,}/mo, ${headroom:,} under your budget")
        elif headroom >= 0:
            parts.append(f"right at your ${int(budget):,}/mo budget")

    matched = [t for t in quality_tags if t.lower() in (listing.tags or '').lower()]
    if matched:
        if len(matched) >= 3:
            parts.append(f"it has all your must-haves: {', '.join(matched)}")
        elif len(matched) == 2:
            parts.append(f"it includes {matched[0]} and {matched[1]}")
        else:
            parts.append(f"it has {matched[0]}")

    tags_lower = (listing.tags or '').lower()
    perks = []
    if 'pet-friendly' in tags_lower and 'pet-friendly' not in [t.lower() for t in quality_tags]:
        perks.append('pet-friendly')
    if 'no deposit' in tags_lower or 'no-deposit' in tags_lower:
        perks.append('no deposit required')
    if 'furnished' in tags_lower and 'furnished' not in [t.lower() for t in quality_tags]:
        perks.append('fully furnished')
    if perks:
        parts.append(f"bonus: {', '.join(perks[:2])}")

    age_days = (timezone.now() - listing.created_at).days
    if age_days == 0:
        parts.append("just listed today — move fast")
    elif age_days <= 3:
        parts.append(f"listed {age_days}d ago, still fresh")

    if not parts:
        if listing.city:
            return f"Located in {listing.city} and within your search criteria."
        return None
    if len(parts) == 1:
        sentence = f"Good fit: {parts[0]}."
    elif len(parts) == 2:
        sentence = f"Good fit: {parts[0]}, and {parts[1]}."
    else:
        sentence = f"Good fit: {parts[0]}. Also — {', '.join(parts[1:])}."
    return sentence[0].upper() + sentence[1:]
