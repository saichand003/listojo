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


def _score_tags(requested_tags: list[str], text_blob: str) -> tuple[int, int, int, list[str]]:
    """Score tag matches against a text blob. Returns (pts, max_pts, tag_hits, reasons)."""
    pts, max_pts, tag_hits = 0, 0, 0
    reasons: list[str] = []
    for tag in requested_tags:
        max_pts += 15
        tag_l = tag.lower().strip()
        if tag_l in text_blob:
            pts += 15
            tag_hits += 1
            reasons.append(_TAG_LABELS.get(tag_l, tag.title()))
        else:
            close = _TAG_RELATED.get(tag_l, [])
            if any(r in text_blob for r in close):
                pts += 5
                reasons.append(f"Similar to {tag}")
    return pts, max_pts, tag_hits, reasons


def _format_explanation(parts: list[str], fallback_location: str | None = None) -> str | None:
    """Build the 'Good fit: …' sentence from a list of reason fragments."""
    if not parts:
        return f"Good fit: located in {fallback_location} and aligned with your search criteria." if fallback_location else None
    if len(parts) == 1:
        sentence = f"Good fit: {parts[0]}."
    elif len(parts) == 2:
        sentence = f"Good fit: {parts[0]}, and {parts[1]}."
    else:
        sentence = f"Good fit: {parts[0]}. Also — {', '.join(parts[1:])}."
    return sentence[0].upper() + sentence[1:]


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
                # Linear from 28 (at budget) to 40 (100% under budget).
                # Old formula capped at ratio=0.5, making cheap listings indistinguishable.
                pts += 28 + min(12, int(ratio * 12))
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
        t_pts, t_max, tag_hits, tag_reasons = _score_tags(requested_tags, tags_lower)
        pts += t_pts
        max_pts += t_max
        reasons.extend(tag_reasons)

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

    return _format_explanation(parts, listing.city or None)


def score_community(
    community,
    *,
    max_price: float | None = None,
    requested_tags: list[str] | None = None,
    property_type: str = '',
    bedrooms: int | None = None,
) -> MatchResult:
    pts, max_pts = 0, 0
    reasons: list[str] = []
    caveats: list[str] = []
    tag_hits = 0

    amenity_blob = ' '.join([
        community.community_amenities or '',
        community.in_unit_amenities or '',
        community.description or '',
        community.special_offer or '',
        community.pet_policy or '',
        community.parking_info or '',
        community.utilities_included or '',
    ]).lower()

    min_price, _ = community.price_range
    available_bedrooms = set(community.bedroom_types)

    if max_price and max_price > 0:
        max_pts += 40
        if min_price is not None:
            starting_price = float(min_price)
            headroom = float(max_price) - starting_price
            if headroom >= 0:
                ratio = headroom / float(max_price)
                pts += 28 + min(12, int(ratio * 12))
                if headroom >= 100:
                    reasons.append(f"From ${int(starting_price):,}/mo")
                else:
                    reasons.append("Within budget")
            elif headroom >= -float(max_price) * 0.10:
                pts += 12
                caveats.append("Slightly over budget")
            else:
                caveats.append("Over budget")
        else:
            pts += 20

    if bedrooms is not None:
        max_pts += 10
        if bedrooms in available_bedrooms:
            pts += 10
            reasons.append("Has your bedroom count")

    community_type_label = community.get_community_type_display() if community.community_type else ''
    if property_type:
        max_pts += 10
        expected_label = {
            'apartment': 'Apartment Complex',
            'condo': 'Condo Building',
            'townhouse': 'Townhouse Complex',
        }.get(property_type)
        if expected_label and community_type_label == expected_label:
            pts += 10
            reasons.append(community_type_label)

    if requested_tags:
        t_pts, t_max, tag_hits, tag_reasons = _score_tags(requested_tags, amenity_blob)
        pts += t_pts
        max_pts += t_max
        reasons.extend(tag_reasons)

    age_days = (timezone.now() - community.created_at).days
    if age_days <= 7:
        pts += 5
        max_pts += 5
        reasons.append("Recently added" if age_days else "Just added")

    if community.featured:
        pts += 2
        max_pts += 2

    if max_pts == 0:
        return MatchResult(70, reasons[:5], caveats[:2], tag_hits)

    pct = int(round(pts / max_pts * 100))
    return MatchResult(min(100, max(0, pct)), reasons[:5], caveats[:2], tag_hits)


def explain_community_match(
    community,
    reasons: list[str],
    *,
    max_price: float | None = None,
    quality_tags: list[str] | None = None,
    property_type: str = '',
) -> str | None:
    parts: list[str] = []
    quality_tags = quality_tags or []

    community_type_label = community.get_community_type_display() if community.community_type else ''
    if property_type == 'apartment' and community.community_type == 'apartment_complex':
        parts.append("it's an apartment complex, which matches the apartment search you selected")
    elif property_type == 'condo' and community.community_type == 'condo_building':
        parts.append("it's a condo building that matches your selected property type")
    elif property_type == 'townhouse' and community.community_type == 'townhouse_complex':
        parts.append("it's a townhouse complex that matches your selected property type")
    elif community_type_label:
        parts.append(f"it offers {community_type_label.lower()} inventory")

    min_price, _ = community.price_range
    if min_price is not None and max_price:
        starting_price = float(min_price)
        budget = float(max_price)
        headroom = int(budget - starting_price)
        if headroom >= 300:
            parts.append(f"units start at ${int(starting_price):,}/mo, well under your ${int(budget):,} budget")
        elif headroom >= 0:
            parts.append(f"units start at ${int(starting_price):,}/mo, within your budget")

    amenity_blob = ' '.join([
        community.community_amenities or '',
        community.in_unit_amenities or '',
        community.description or '',
        community.special_offer or '',
    ]).lower()
    matched = [t for t in quality_tags if t.lower() in amenity_blob]
    if matched:
        if len(matched) >= 3:
            parts.append(f"it covers several of your must-haves: {', '.join(matched[:3])}")
        elif len(matched) == 2:
            parts.append(f"it includes {matched[0]} and {matched[1]}")
        else:
            parts.append(f"it includes {matched[0]}")

    if community.available_unit_count:
        parts.append(f"{community.available_unit_count} unit{'s' if community.available_unit_count != 1 else ''} available")

    return _format_explanation(parts, community.city or None)
