from __future__ import annotations

from datetime import date
from typing import NamedTuple

from django.utils import timezone


# A listing without one of the renter's must-haves is at best a partial fit,
# however well it does on everything else.
MISSING_MUST_HAVE_CAP = 69


class MatchResult(NamedTuple):
    # None when there was nothing to score against: a percentage computed
    # from no preferences is a constant, not a match.
    pct: int | None
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


# What an included-utilities listing is worth against a budget, per month.
UTILITIES_CREDIT = 150

_UTILITY_TAGS = ('utilities included', 'bills included', 'all bills paid')


def utilities_included(listing) -> bool:
    """
    One answer to "are utilities included?". Landlords set it as the field or
    as a tag, sometimes only one of the two, so either counts.
    """
    if getattr(listing, 'bills_included', False):
        return True
    tags = (getattr(listing, 'tags', '') or '').lower()
    return any(t in tags for t in _UTILITY_TAGS)


def match_band(pct: int | None) -> str | None:
    """The one set of thresholds every surface uses to label a score."""
    if pct is None:
        return None
    return 'strong' if pct >= 85 else 'fair' if pct >= 65 else 'weak'


def match_badge_class(pct: int | None) -> str:
    """CSS modifier for .match-score-badge (high / mid / low)."""
    return {'strong': 'high', 'fair': 'mid', 'weak': 'low'}.get(match_band(pct), '')


def _score_bedrooms(wanted: int | None, actual: int | None) -> tuple[int, int, list[str], list[str]]:
    """
    Bedrooms out of 10. Zero is a studio, not "no answer". One more bedroom
    than asked for is a partial fit; fewer is a miss worth calling out.
    """
    if wanted is None or actual is None:
        return 0, 0, [], []
    if actual == wanted:
        label = 'Studio' if actual == 0 else f"{actual} bed match"
        return 10, 10, [label], []
    if actual == wanted + 1:
        return 6, 10, [f"{actual} bed (one extra)"], []
    if actual > wanted:
        return 3, 10, [], []
    return 0, 10, [], [f"Only {actual} bed" if actual else "Studio only"]


def _score_tags(requested_tags: list[str], text_blob: str) -> tuple[int, int, int, list[str], list[str]]:
    """
    Score tag matches against a text blob.
    Returns (pts, max_pts, tag_hits, reasons, missing) — `missing` names the
    must-haves with no match at all, so the card can say what it lacks.
    """
    pts, max_pts, tag_hits = 0, 0, 0
    reasons: list[str] = []
    missing: list[str] = []
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
            else:
                missing.append(f"No {tag_l}")
    return pts, max_pts, tag_hits, reasons, missing


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
    tag_missing: list[str] = []
    tags_lower = (listing.tags or '').lower()

    if max_price and max_price > 0:
        max_pts += 40
        if listing.price:
            price = float(listing.price)
            bills = utilities_included(listing)
            effective = price - (UTILITIES_CREDIT if bills else 0)
            headroom = float(max_price) - effective
            if headroom >= 0:
                ratio = headroom / float(max_price)
                # Linear from 28 (at budget) to 40 (100% under budget).
                # Old formula capped at ratio=0.5, making cheap listings indistinguishable.
                pts += 28 + min(12, int(ratio * 12))
                if bills:
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

    b_pts, b_max, b_reasons, b_caveats = _score_bedrooms(bedrooms, listing.bedrooms)
    pts += b_pts
    max_pts += b_max
    reasons.extend(b_reasons)
    caveats.extend(b_caveats)

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
        t_pts, t_max, tag_hits, tag_reasons, tag_missing = _score_tags(requested_tags, tags_lower)
        pts += t_pts
        max_pts += t_max
        reasons.extend(tag_reasons)
        caveats.extend(tag_missing)

    if avail_date:
        max_pts += 10
        if not listing.available_from or listing.available_from <= avail_date:
            pts += 10
            reasons.append("Available now" if not listing.available_from else "Meets move-in date")

    # Nothing asked for, nothing to measure.
    if max_pts == 0:
        return MatchResult(None, [], [], 0)

    # Freshness and "no deposit" are worth saying but not worth points: they
    # were only ever added when true, so they pushed scores toward 100
    # regardless of fit. Featured (paid) placement never touches the score.
    age_days = (timezone.now() - listing.created_at).days
    if age_days <= 3:
        reasons.append("Just listed" if age_days == 0 else f"Listed {age_days}d ago")
    if 'no deposit' in tags_lower or 'no-deposit' in tags_lower:
        reasons.append("No deposit")

    pct = int(round(pts / max_pts * 100))
    if tag_missing:
        pct = min(pct, MISSING_MUST_HAVE_CAP)
    return MatchResult(min(100, max(0, pct)), reasons[:5], caveats[:3], tag_hits)


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
    if base.pct is not None and priority and listing.price and preference.max_budget:
        price = float(listing.price)
        budget = float(preference.max_budget)
        if priority == 'price' and price <= budget:
            boosted = min(100, base.pct + 8)
            return MatchResult(boosted, base.reasons, base.caveats, base.tag_hits)
        if priority == 'features' and base.tag_hits >= 2:
            boosted = min(100, base.pct + 6)
            return MatchResult(boosted, base.reasons, base.caveats, base.tag_hits)

    return base


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
    tag_missing: list[str] = []

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

    if bedrooms is not None and available_bedrooms:
        max_pts += 10
        if bedrooms in available_bedrooms:
            pts += 10
            reasons.append("Has your bedroom count")
        elif bedrooms + 1 in available_bedrooms:
            pts += 6
            reasons.append(f"Has {bedrooms + 1}-bed units")
        else:
            caveats.append("No units with your bedroom count")

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
        t_pts, t_max, tag_hits, tag_reasons, tag_missing = _score_tags(requested_tags, amenity_blob)
        pts += t_pts
        max_pts += t_max
        reasons.extend(tag_reasons)
        caveats.extend(tag_missing)

    if max_pts == 0:
        return MatchResult(None, [], [], 0)

    age_days = (timezone.now() - community.created_at).days
    if age_days <= 7:
        reasons.append("Recently added" if age_days else "Just added")

    pct = int(round(pts / max_pts * 100))
    if tag_missing:
        pct = min(pct, MISSING_MUST_HAVE_CAP)
    return MatchResult(min(100, max(0, pct)), reasons[:5], caveats[:3], tag_hits)
