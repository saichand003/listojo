"""
Whose preferences a match score is measured against.

A score is only honest against preferences someone actually gave us, and it is
only trustworthy if the same listing gets the same number everywhere. So every
surface — search cards, the detail page, the "get your match score" sheet —
resolves preferences through this one module, in one order:

    1. The criteria remembered in this session (the latest guided search or
       match-score sheet the visitor filled in).
    2. The signed-in visitor's most recent saved search.

Find-My-Match results score against the URL instead, and remember those
criteria here, so the detail page a card links to scores against the same thing.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from listings.services.matching import (
    MatchResult,
    explain_community_match,
    explain_match,
    score_community,
    score_listing,
)

SESSION_KEY = 'gs_criteria'


def _to_float(v) -> float | None:
    if isinstance(v, str):
        v = v.replace('$', '').replace(',', '').strip()
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f > 0 else None


def _to_int(v) -> int | None:
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _to_date(v) -> date | None:
    try:
        return date.fromisoformat(v)
    except (TypeError, ValueError):
        return None


def _split_tags(raw) -> list[str]:
    return [t.strip() for t in (raw or '').split(',') if t.strip()]


@dataclass
class MatchPrefs:
    max_price: float | None = None
    tags: list[str] = field(default_factory=list)
    bedrooms: int | None = None
    property_type: str = ''
    accommodation_type: str = ''
    avail_date: date | None = None
    source: str = ''

    @property
    def has_criteria(self) -> bool:
        return any([
            self.max_price, self.tags, self.bedrooms is not None,
            self.property_type, self.accommodation_type, self.avail_date,
        ])

    def score(self, listing) -> MatchResult:
        return score_listing(
            listing,
            max_price=self.max_price,
            requested_tags=self.tags,
            avail_date=self.avail_date,
            accommodation_type=self.accommodation_type,
            property_type=self.property_type,
            bedrooms=self.bedrooms,
        )

    def score_community(self, community) -> MatchResult:
        return score_community(
            community,
            max_price=self.max_price,
            requested_tags=self.tags,
            property_type=self.property_type,
            bedrooms=self.bedrooms,
        )

    def explain(self, listing, reasons) -> str | None:
        return explain_match(
            listing, reasons,
            max_price=self.max_price,
            quality_tags=self.tags,
            accommodation_type=self.accommodation_type,
            property_type=self.property_type,
        )

    def explain_community(self, community, reasons) -> str | None:
        return explain_community_match(
            community, reasons,
            max_price=self.max_price,
            quality_tags=self.tags,
            property_type=self.property_type,
        )

    def as_form_initial(self) -> dict:
        return {
            'max_price': int(self.max_price) if self.max_price else '',
            'bedrooms': '' if self.bedrooms is None else self.bedrooms,
            'tags': self.tags,
        }


def from_mapping(data, source: str) -> MatchPrefs:
    """Build prefs from URL params, POST data or the session dict (same keys)."""
    return MatchPrefs(
        max_price=_to_float(data.get('max_price')),
        tags=_split_tags(data.get('tags')),
        bedrooms=_to_int(data.get('bedrooms')),
        property_type=(data.get('property_type') or '').strip(),
        accommodation_type=(data.get('accommodation_type') or '').strip(),
        avail_date=_to_date(data.get('available_by')),
        source=source,
    )


def remember(request, prefs: MatchPrefs) -> None:
    """Keep these criteria for the rest of the visit."""
    request.session[SESSION_KEY] = {
        'max_price': prefs.max_price or '',
        'tags': ','.join(prefs.tags),
        'bedrooms': '' if prefs.bedrooms is None else prefs.bedrooms,
        'property_type': prefs.property_type,
        'accommodation_type': prefs.accommodation_type,
        'available_by': prefs.avail_date.isoformat() if prefs.avail_date else '',
    }


def forget(request) -> None:
    request.session.pop(SESSION_KEY, None)


def resolve_match_prefs(request) -> MatchPrefs | None:
    """The visitor's preferences, or None when they have given us none."""
    stored = request.session.get(SESSION_KEY)
    if stored:
        prefs = from_mapping(stored, 'your match preferences')
        if prefs.has_criteria:
            return prefs

    if request.user.is_authenticated:
        from listings.models import SavedSearch
        saved = (SavedSearch.objects
                 .filter(user=request.user)
                 .order_by('-last_updated')
                 .first())
        if saved:
            prefs = MatchPrefs(
                max_price=_to_float(saved.max_budget),
                tags=_split_tags(saved.amenities),
                bedrooms=saved.bedrooms,
                property_type=saved.property_type or '',
                accommodation_type=saved.accommodation_type or '',
                avail_date=_to_date(saved.available_by),
                source='your saved search',
            )
            if prefs.has_criteria:
                return prefs

    return None
