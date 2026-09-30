"""
The Fit Report: how a listing fits this renter — never a grade on the property.

Listojo is two-sided. Renters need to know why a place suits them; landlords
and communities list here to fill units, so nothing a renter sees may read as
a mark against the home. The report therefore follows "fit, not flaws":

1. Every claim comes from a field we hold. A fact we don't have is shown as
   "not available yet", never guessed, and the report says how many factors it
   could actually check ("based on 4 of 6").
2. The fit percentage only counts what the renter asked for (budget, bedrooms,
   must-haves, move-in). Commute, groceries, schools and walkability are
   neutral "good to know" facts: they never move the number and are never
   scored in front of the renter.
3. The only downside shown is a mismatch with the renter's OWN criteria —
   over their budget, a must-have not listed, fewer bedrooms, a later move-in —
   worded neutrally. Hiding those would only waste the landlord's tour slot.
4. Comparisons across the renter's matches are positive-only ("cheapest of
   your 5 matches"); no listing is ever called the worst of anything.
5. Reasons are chosen by what tells this listing apart: a strength every match
   shares ("2 bed, as asked") says nothing and is dropped.

Gaps a landlord can fix (no photos, no square footage) are not renter-facing
at all — see listings.services.listing_strength, shown in the landlord portal.

Usage:
    reports = build_reports(listings, prefs)             # {pk: FitReport} for a results page
    report  = build_report(listing, prefs, detail=True)  # one listing, for its page
"""
from __future__ import annotations

from dataclasses import dataclass, field

from listings.services.matching import (
    UTILITIES_CREDIT,
    _TAG_RELATED,
    match_band,
    utilities_included,
)

BAND_LABELS = {'strong': 'Excellent fit', 'fair': 'Good fit', 'weak': 'Partial fit'}

# Two matches is already a choice the renter is making, so compare from two.
MIN_TO_COMPARE = 2


@dataclass
class Dimension:
    key: str
    label: str
    score: int | None          # 0-100 for the renter's criteria; for context, internal only
    evidence: str              # the fact, in words
    source: str = ''
    counted: bool = True       # a criterion the renter gave us, or a context fact
    metric: float | None = None  # raw value used to compare across matches

    @property
    def available(self) -> bool:
        return self.score is not None


@dataclass
class _Candidate:
    key: str
    text: str
    weight: int


@dataclass
class FitReport:
    pct: int
    band: str
    label: str
    dimensions: list[Dimension]
    strengths: list[str] = field(default_factory=list)
    best_of: str | None = None
    # Where the listing doesn't meet what the renter asked for, in their terms.
    mismatches: list[str] = field(default_factory=list)
    covered: int = 0
    possible: int = 0
    sources: list[str] = field(default_factory=list)

    @property
    def criteria(self) -> list[Dimension]:
        return [d for d in self.dimensions if d.counted]

    @property
    def good_to_know(self) -> list[Dimension]:
        return [d for d in self.dimensions if not d.counted]


# ── Reading an item ─────────────────────────────────────────────────────────

def _money(v: float) -> str:
    return f"${int(round(v)):,}"


def _falloff(value: float, full_at: float, zero_at: float) -> int:
    """100 at or better than `full_at`, 0 at or worse than `zero_at`, linear between."""
    if value <= full_at:
        return 100
    if value >= zero_at:
        return 0
    return int(round(100 * (zero_at - value) / (zero_at - full_at)))


class _Subject:
    """The handful of facts the report needs, from a Listing or a Community."""

    def __init__(self, item):
        from listings.models import Community
        self.item = item
        self.is_community = isinstance(item, Community)
        if self.is_community:
            low, _ = item.price_range
            self.price = float(low) if low else None
            self.monthly = True
            self.from_price = True
            self.bills = False
            self.blob = ' '.join(filter(None, [
                item.community_amenities, item.in_unit_amenities, item.description,
                item.special_offer, item.pet_policy, item.parking_info, item.utilities_included,
            ])).lower()
            self.bedroom_set = set(item.bedroom_types)
            self.bedrooms = None
            self.available_from = None
        else:
            self.price = float(item.price) if item.price else None
            self.monthly = item.category != 'properties' and item.price_unit in ('', 'mo')
            self.from_price = False
            self.bills = self.monthly and utilities_included(item)
            self.blob = (item.tags or '').lower()
            self.bedroom_set = None
            self.bedrooms = item.bedrooms
            self.available_from = item.available_from

    @property
    def effective_price(self) -> float | None:
        if self.price is None:
            return None
        return self.price - (UTILITIES_CREDIT if self.bills else 0)

    @property
    def per(self) -> str:
        return '/mo' if self.monthly else ''

    def related(self, name):
        rel = getattr(self.item, name, None)
        return list(rel.all()) if rel is not None else []


# ── The renter's criteria (counted in the %) ────────────────────────────────
# Each returns (Dimension, mismatch-or-None).

def _budget(s: _Subject, prefs):
    if not prefs.max_price:
        return None, None
    budget = float(prefs.max_price)
    eff = s.effective_price
    if eff is None:
        return Dimension('budget', 'Budget', None, 'Price not listed'), None
    headroom = budget - eff
    price_txt = ('From ' if s.from_price else '') + _money(eff) + s.per
    if s.bills:
        price_txt += f" after utilities (included, worth ~{_money(UTILITIES_CREDIT)})"
    if headroom >= 0:
        score = 70 + int(round(30 * min(1.0, headroom / (0.3 * budget))))
        evidence = f"{price_txt} · {_money(headroom)} under your {_money(budget)} budget" if headroom >= 25 \
            else f"{price_txt} · right at your {_money(budget)} budget"
        return Dimension('budget', 'Budget', score, evidence, metric=eff), None
    over = -headroom
    score = max(0, int(round(60 - over / budget * 400)))
    miss = f"{_money(over)} over your {_money(budget)} budget"
    return Dimension('budget', 'Budget', score, f"{price_txt} · {miss}", metric=eff), miss


def _bed_label(n: int) -> str:
    return 'Studio' if n == 0 else f"{n} bed"


def _space(s: _Subject, prefs):
    want = prefs.bedrooms
    if want is None:
        return None, None
    want_txt = _bed_label(want).lower()
    if s.is_community:
        if not s.bedroom_set:
            return Dimension('space', 'Bedrooms', None, 'Floor plans not listed'), None
        if want in s.bedroom_set:
            return Dimension('space', 'Bedrooms', 100, f"Has {want_txt} units, as asked"), None
        if want + 1 in s.bedroom_set:
            return Dimension('space', 'Bedrooms', 70, f"Has {want + 1} bed units"), None
        miss = f"No {want_txt} units listed"
        return Dimension('space', 'Bedrooms', 0, miss), miss
    have = s.bedrooms
    if have is None:
        return Dimension('space', 'Bedrooms', None, 'Bedrooms not listed'), None
    if have == want:
        return Dimension('space', 'Bedrooms', 100, f"{_bed_label(have)}, as asked"), None
    if have == want + 1:
        return Dimension('space', 'Bedrooms', 70, f"{_bed_label(have)}, one more than you asked for"), None
    if have > want:
        return Dimension('space', 'Bedrooms', 40, f"{_bed_label(have)}, more than you asked for"), None
    miss = f"{_bed_label(have)}; you asked for {want_txt}"
    return Dimension('space', 'Bedrooms', 0, miss), miss


def _must_haves(s: _Subject, prefs):
    """(Dimension, mismatch, met tags)."""
    if not prefs.tags:
        return None, None, []
    met, near, missing = [], [], []
    for tag in prefs.tags:
        t = tag.lower().strip()
        if t in s.blob:
            met.append(tag)
        elif any(r in s.blob for r in _TAG_RELATED.get(t, [])):
            near.append(tag)
        else:
            missing.append(tag)
    score = int(round((len(met) + 0.4 * len(near)) / len(prefs.tags) * 100))
    parts = [f"{t} ✓" for t in met] + [f"{t} (similar)" for t in near] + [f"{t}: not listed" for t in missing]
    dim = Dimension('musthaves', 'Must-haves', score, ' · '.join(parts), metric=len(met) / len(prefs.tags))
    miss = f"Doesn't list: {', '.join(missing)}" if missing else None
    return dim, miss, met


def _move_in(s: _Subject, prefs):
    if not prefs.avail_date or s.is_community:
        return None, None
    when = s.available_from
    if not when or when <= prefs.avail_date:
        txt = 'Available now' if not when else f"Available {when:%b} {when.day}, before your move-in"
        return Dimension('movein', 'Move-in', 100, txt), None
    miss = f"Available {when:%b} {when.day}, after your {prefs.avail_date:%b} {prefs.avail_date.day} move-in"
    return Dimension('movein', 'Move-in', 0, miss), miss


# ── Good to know: facts about the place (never scored in front of renters) ──

def _commute(s: _Subject) -> Dimension:
    item = s.item
    parts, minutes = [], getattr(item, 'downtown_drive_minutes', None)
    downtown = getattr(item, 'nearest_downtown', None)
    if minutes and downtown:
        parts.append(f"{minutes} min drive to {downtown.name}")
    stations = s.related('nearby_transit')
    if stations:
        link = stations[0]
        walk = getattr(link, 'walk_minutes', None)
        where = f"{walk} min walk" if walk else f"{link.distance_miles} mi"
        parts.append(f"{link.station.name} ({link.station.get_mode_display().lower()}), {where}")
    score = getattr(item, 'commute_score', None)
    if score is None and minutes:
        score = _falloff(minutes, 15, 60)
    if score is None or not parts:
        return Dimension('commute', 'Getting around', None, 'Not available yet for this address', counted=False)
    return Dimension('commute', 'Getting around', score, ' · '.join(parts), 'Google Routes',
                     counted=False, metric=float(minutes) if minutes else None)


def _errands(s: _Subject) -> Dimension:
    stores = [g for g in s.related('nearby_groceries') if g.drive_minutes or g.distance_miles]
    if not stores:
        return Dimension('errands', 'Groceries', None, 'Not available yet for this address', counted=False)
    nearest = min(stores, key=lambda g: (g.drive_minutes or 99, float(g.distance_miles or 99)))
    chain = nearest.store.chain or nearest.store.name
    if nearest.drive_minutes:
        return Dimension('errands', 'Groceries', _falloff(nearest.drive_minutes, 5, 25),
                         f"{chain}, {nearest.drive_minutes} min drive", 'Google Places',
                         counted=False, metric=float(nearest.drive_minutes))
    miles = float(nearest.distance_miles)
    return Dimension('errands', 'Groceries', _falloff(miles, 1, 8), f"{chain}, {miles:g} mi",
                     'Google Places', counted=False, metric=miles * 2.5)


def _schools(s: _Subject) -> Dimension | None:
    if s.is_community:
        return None
    rated = [l for l in s.related('nearby_schools') if l.school.rating]
    if not rated:
        return Dimension('schools', 'Schools', None, 'Not available yet for this address', counted=False)
    nearest = min(rated, key=lambda l: float(l.distance_miles or 99))
    dist = f", {nearest.distance_miles} mi" if nearest.distance_miles is not None else ''
    return Dimension('schools', 'Schools', nearest.school.rating * 10,
                     f"{nearest.school.name}{dist} · rated {nearest.school.rating}/10", 'GreatSchools',
                     counted=False, metric=float(nearest.school.rating))


def _walkability(s: _Subject) -> Dimension:
    score = getattr(s.item, 'walk_score', None)
    if score is None:
        return Dimension('walk', 'Walkability', None, 'Not available yet for this address', counted=False)
    desc = getattr(s.item, 'walk_score_description', '') or ''
    return Dimension('walk', 'Walkability', score, f"Walk Score {score}" + (f" · {desc}" if desc else ''),
                     'Walk Score', counted=False, metric=float(score))


def _market(s: _Subject) -> Dimension | None:
    """
    Price against the Listojo price model — detail page only (it loads a
    model). Shown only when the listing is at or below the estimate: a price
    above it is the landlord's call, and not something to grade in public.
    """
    if s.is_community or not s.monthly or s.price is None:
        return None
    try:
        from listings.services.valuation import predict_price
        est = predict_price(s.item)
    except Exception:  # noqa: BLE001 — a missing or broken model must never break a page
        est = None
    if not est or not est.get('estimate') or est.get('confidence') == 'low':
        return None
    estimate = float(est['estimate'])
    pct = (s.price - estimate) / estimate * 100
    if pct > 3:
        return None
    txt = (f"In line with similar homes (Listojo estimate {_money(estimate)})" if pct > -3
           else f"{_money(estimate - s.price)} below similar homes (Listojo estimate {_money(estimate)})")
    return Dimension('market', 'Price vs similar homes', 60 - int(round(pct * 4)), txt,
                     'Listojo price model', counted=False, metric=pct)


# ── Strengths ───────────────────────────────────────────────────────────────

def _priority_weight(prefs, key: str) -> int:
    favoured = {
        'price': {'budget', 'market'},
        'location': {'commute', 'errands', 'walk'},
        'features': {'musthaves'},
    }.get(getattr(prefs, 'priority', '') or '', set())
    return 3 if key in favoured else 1


def _strengths(dims: dict[str, Dimension], met: list[str], prefs) -> list[_Candidate]:
    out = []

    def add(key, text):
        out.append(_Candidate(key, text, _priority_weight(prefs, key)))

    d = dims.get('budget')
    if d and d.available and d.score >= 80 and d.metric is not None:
        add('budget', f"{_money(float(prefs.max_price) - d.metric)} under budget")
    d = dims.get('musthaves')
    if d and d.score == 100:
        add('musthaves', 'Every must-have: ' + ', '.join(met))
    d = dims.get('space')
    if d and d.score == 100:
        add('space', d.evidence)
    d = dims.get('movein')
    if d and d.score == 100:
        add('movein', 'Ready by your move-in')
    d = dims.get('commute')
    if d and d.available and d.score >= 70:
        add('commute', d.evidence.split(' · ')[0])
    d = dims.get('errands')
    if d and d.available and d.score >= 75:
        add('errands', f"Groceries nearby: {d.evidence}")
    d = dims.get('schools')
    if d and d.available and d.score >= 80:
        add('schools', f"Well-rated school nearby: {d.evidence}")
    d = dims.get('walk')
    if d and d.available and d.score >= 70:
        add('walk', d.evidence)
    d = dims.get('market')
    if d and d.metric is not None and d.metric <= -3:
        add('market', d.evidence)
    return out


def _top_facts(dims, limit: int = 2) -> list[str]:
    """
    The place's best measured facts, when nothing stands out as a distinct
    strength — so a card always says something concrete about the home.
    """
    facts = sorted((d for d in dims.values() if not d.counted and d.available), key=lambda d: -d.score)
    return [d.evidence for d in facts[:limit]]


# ── Building reports ────────────────────────────────────────────────────────

_ORDER = ['budget', 'space', 'musthaves', 'movein', 'commute', 'errands', 'schools', 'walk', 'market']


def _dimensions(s: _Subject, prefs, detail: bool):
    """(dims by key, mismatches, met must-haves)."""
    dims: dict[str, Dimension] = {}
    mismatches: list[str] = []
    for dim, miss in (_budget(s, prefs), _space(s, prefs)):
        if dim:
            dims[dim.key] = dim
        if miss:
            mismatches.append(miss)
    must, miss, met = _must_haves(s, prefs)
    if must:
        dims[must.key] = must
    if miss:
        mismatches.append(miss)
    dim, miss = _move_in(s, prefs)
    if dim:
        dims[dim.key] = dim
    if miss:
        mismatches.append(miss)
    for d in (_commute(s), _errands(s), _schools(s), _walkability(s)):
        if d:
            dims[d.key] = d
    if detail:
        d = _market(s)
        if d:
            dims[d.key] = d
    return dims, mismatches, met


def _assemble(pct: int, dims, strengths, mismatches, best_of) -> FitReport:
    ordered = [dims[k] for k in _ORDER if k in dims]
    covered = [d for d in ordered if d.available]
    sources = []
    for d in covered:
        for src in filter(None, (x.strip() for x in d.source.split('·'))):
            if src not in sources:
                sources.append(src)
    band = match_band(pct)
    return FitReport(
        pct=pct, band=band, label=BAND_LABELS[band], dimensions=ordered,
        strengths=strengths, best_of=best_of, mismatches=mismatches,
        covered=len(covered), possible=len(ordered), sources=sources,
    )


def _score(item, prefs):
    from listings.models import Community
    return prefs.score_community(item) if isinstance(item, Community) else prefs.score(item)


def build_report(item, prefs, *, detail: bool = False) -> FitReport | None:
    """One listing on its own — its page, where there's no result set to compare to."""
    result = _score(item, prefs)
    if result.pct is None:
        return None
    dims, mismatches, met = _dimensions(_Subject(item), prefs, detail)
    cands = sorted(_strengths(dims, met, prefs), key=lambda c: -c.weight)
    strengths = [c.text for c in cands[:3]] or _top_facts(dims)
    return _assemble(result.pct, dims, strengths, mismatches, None)


# Positive-only comparisons across a results page: metric, which direction is
# better, and how to say it (with two matches, "than your other match").
_COMPARISONS = {'budget': 'low', 'commute': 'low', 'errands': 'low', 'schools': 'high', 'walk': 'high'}


def _best_phrase(key, n, v, gap, total=None):
    if total is not None and n < total:
        # Only some matches have this data: don't pass a partial count off as all of them.
        return {
            'budget': f"Cheapest of your matches, {_money(gap)} less than the next",
            'commute': f"Shortest drive to downtown among your matches with drive data ({int(v)} min)",
            'errands': "Closest groceries among your matches with grocery data",
            'schools': f"Highest-rated nearby school among your matches with ratings ({int(v)}/10)",
            'walk': f"Most walkable among your matches with a Walk Score ({int(v)})",
        }[key]
    if n == 2:
        return {
            'budget': f"Cheaper than your other match by {_money(gap)}",
            'commute': f"Shorter drive to downtown than your other match ({int(v)} min)",
            'errands': "Closer to groceries than your other match",
            'schools': f"Higher-rated nearby school than your other match ({int(v)}/10)",
            'walk': f"More walkable than your other match (Walk Score {int(v)})",
        }[key]
    return {
        'budget': f"Cheapest of your {n} matches, {_money(gap)} less than the next",
        'commute': f"Shortest drive to downtown of your {n} matches ({int(v)} min)",
        'errands': f"Closest groceries of your {n} matches",
        'schools': f"Highest-rated nearby school of your {n} matches ({int(v)}/10)",
        'walk': f"Most walkable of your {n} matches (Walk Score {int(v)})",
    }[key]


def _comparison_order(prefs) -> list[str]:
    first = {'price': ['budget'], 'location': ['commute', 'errands', 'walk']}.get(
        getattr(prefs, 'priority', '') or '', [])
    return first + [k for k in ('budget', 'commute', 'errands', 'schools', 'walk') if k not in first]


def build_reports(items, prefs) -> dict:
    """
    Reports for a whole results page, keyed by pk. The page is what makes
    "best of your N" and "drop what every match shares" possible.
    """
    rows = []
    for item in items:
        result = _score(item, prefs)
        if result.pct is None:
            continue
        dims, mismatches, met = _dimensions(_Subject(item), prefs, detail=False)
        rows.append((item, result.pct, dims, mismatches, met))
    if not rows:
        return {}

    # A strength every match shares tells the renter nothing about this one.
    cand_by_pk = {r[0].pk: _strengths(r[2], r[4], prefs) for r in rows}
    shared = set()
    if len(rows) >= 2:
        shared = set.intersection(*({c.key for c in cands} for cands in cand_by_pk.values()))

    best_of: dict = {}
    for key in _comparison_order(prefs):
        better = _COMPARISONS[key]
        values = [(r[0].pk, r[2][key].metric) for r in rows
                  if key in r[2] and r[2][key].metric is not None and r[2][key].available]
        if len(values) < MIN_TO_COMPARE:
            continue
        ranked = sorted(values, key=lambda kv: kv[1], reverse=(better == 'high'))
        (top_pk, top_v), (_, next_v) = ranked[0], ranked[1]
        if top_v != next_v and top_pk not in best_of:
            best_of[top_pk] = (key, _best_phrase(key, len(values), top_v, abs(next_v - top_v),
                                                 total=len(rows)))

    reports = {}
    for item, pct, dims, mismatches, met in rows:
        best = best_of.get(item.pk)
        cands = [c for c in cand_by_pk[item.pk]
                 if c.key not in shared and not (best and c.key == best[0])]
        cands.sort(key=lambda c: -c.weight)
        strengths = [c.text for c in cands[:2]]
        if not strengths and not best:
            strengths = _top_facts(dims)
        reports[item.pk] = _assemble(pct, dims, strengths, mismatches, best[1] if best else None)
    return reports
