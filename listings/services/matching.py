"""
Unified listing match scoring service.

Single source of truth for all scoring logic — used by both the consumer
search flow (FMM) and the agent portal (curated shortlist scoring).
No view or template should duplicate this logic.
"""
from __future__ import annotations

from datetime import date
from typing import NamedTuple

from django.utils import timezone


class MatchResult(NamedTuple):
    pct: int               # 0–100
    reasons: list[str]     # positive signals shown to user/agent
    caveats: list[str]     # soft warnings (over budget, etc.)
    tag_hits: int          # number of requested tags found


# ── Tag synonym map (used for partial credit) ──────────────────────────────
_TAG_RELATED: dict[str, list[str]] = {
    'garage':       ['parking', 'covered parking', 'carport'],
    'lake':         ['waterway', 'water view', 'canal', 'pond', 'pool'],
    'pool':         ['gym', 'amenities', 'community pool'],
    'gym':          ['fitness', 'workout', 'exercise'],
    'pet friendly': ['pet-friendly', 'pets allowed', 'dogs ok'],
    'furnished':    ['fully furnished', 'semi-furnished'],
    'balcony':      ['patio', 'terrace', 'deck', 'outdoor'],
    'gated':        ['secured', 'secure', 'fenced'],
    'schools':      ['near schools', 'good schools', 'school district'],
}

_TAG_LABELS: dict[str, str] = {
    'pet friendly':        'Pet friendly',
    'washer dryer':        'W/D in unit',
    'washer/dryer':        'W/D in unit',
    'parking':             'Parking',
    'central ac':          'Central AC',
    'gym':                 'Gym',
    'pool':                'Pool',
    'furnished':           'Furnished',
    'bills included':      'Bills included',
    'gated':               'Gated',
    'balcony':             'Balcony',
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
    """
    Score a listing against search/preference criteria.

    Works for both consumer FMM searches and agent preference matching.
    Returns a MatchResult with pct, reasons, caveats, tag_hits.
    """
    pts, max_pts = 0, 0
    reasons: list[str] = []
    caveats: list[str] = []
    tag_hits = 0
    tags_lower = (listing.tags or '').lower()

    # ── Budget (40 pts) ──────────────────────────────────────────────────
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
                elif headroom >= 500:
                    reasons.append(f"${int(headroom):,} under budget")
                elif headroom >= 100:
                    reasons.append(f"${int(headroom):,} under budget")
                elif headroom >= 0:
                    reasons.append("Within budget")
            elif headroom >= -float(max_price) * 0.10:
                pts += 12
                caveats.append("Slightly over budget")
            else:
                caveats.append("Over budget")
        else:
            pts += 20  # no price listed — neutral

    # ── Bedrooms (10 pts) ────────────────────────────────────────────────
    if bedrooms and listing.bedrooms:
        max_pts += 10
        if listing.bedrooms == bedrooms:
            pts += 10
            reasons.append(f"{listing.bedrooms} bed match")

    # ── Accommodation type (15 pts) ──────────────────────────────────────
    if accommodation_type:
        max_pts += 15
        if listing.accommodation_type == accommodation_type:
            pts += 15
            label = 'Whole place' if accommodation_type == 'whole' else 'Single room'
            reasons.append(label)

    # ── Property type (10 pts) ───────────────────────────────────────────
    if property_type:
        max_pts += 10
        if listing.property_type == property_type:
            pts += 10
            reasons.append(listing.get_property_type_display())

    # ── Tags / amenities (15 pts each, partial for related) ─────────────
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

    # ── Availability (10 pts) ────────────────────────────────────────────
    if avail_date:
        max_pts += 10
        if not listing.available_from or listing.available_from <= avail_date:
            pts += 10
            reasons.append(
                "Available now" if not listing.available_from else "Meets move-in date"
            )

    # ── Freshness bonus (5 pts) ──────────────────────────────────────────
    age_days = (timezone.now() - listing.created_at).days
    if age_days <= 3:
        pts += 5
        max_pts += 5
        reasons.append("Just listed" if age_days == 0 else f"Listed {age_days}d ago")

    # ── Bonus perks (up to 5 pts) ────────────────────────────────────────
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
    """
    Convenience wrapper: score a listing against a LeadPreference object.
    Used by the agent portal shortlist and curated match views.
    """
    tags = (
        [t.strip() for t in preference.amenities.split(',') if t.strip()]
        if preference.amenities else []
    )
    return score_listing(
        listing,
        max_price=float(preference.max_budget) if preference.max_budget else None,
        requested_tags=tags,
        avail_date=preference.move_in_date,
        property_type=preference.property_type or '',
        bedrooms=preference.bedrooms,
    )
