"""
The Fit Report: what a match score means for this renter, listing by listing.

A bare percentage tells a renter nothing they didn't type into the filters.
The report says what the number is made of, what this place does better than
the other places they're looking at, and what the catch is.

Three rules hold everywhere in this module:

1. Every claim comes from a field we hold. A dimension without data is shown
   as "no data", never guessed, and the report says how many factors it could
   actually check ("based on 4 of 6").
2. The fit percentage only counts what the renter asked for (budget, bedrooms,
   must-haves, move-in). Commute, errands, schools and walkability are shown as
   context — facts about the place — but never move the number, because the
   renter didn't ask us to weigh them.
3. Reasons are chosen by what tells this listing apart. If every match has two
   bedrooms, "2 bed, as asked" is true of all of them and says nothing, so it is
   dropped; "cheapest of your 7 matches" is kept.

Usage:
    reports = build_reports(listings, prefs)          # {pk: FitReport} for a results page
    report  = build_report(listing, prefs, detail=True)  # one listing, with price-vs-market
"""
from __future__ import annotations

from dataclasses import dataclass, field
from statistics import median

from listings.services.matching import (
    UTILITIES_CREDIT,
    _TAG_RELATED,
    match_band,
    utilities_included,
)

BAND_LABELS = {'strong': 'Excellent fit', 'fair': 'Good fit', 'weak': 'Partial fit'}

# A comparison across the results only means something with a few to compare.
MIN_TO_COMPARE = 3


@dataclass
class Dimension:
    key: str
    label: str
    score: int | None          # 0-100; None = we hold no data for it
    evidence: str              # the fact behind the score, in words
    source: str = ''
    counted: bool = True       # part of the fit %, or context only
    metric: float | None = None  # raw value used to compare across matches


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
    catch: str | None = None
    # 'bad' = a real downside, 'clear' = nothing flagged in the data we hold,
    # 'unknown' = too little data to say.
    catch_tone: str = 'bad'
    covered: int = 0
    possible: int = 0
    sources: list[str] = field(default_factory=list)

    @property
    def criteria(self) -> list[Dimension]:
        return [d for d in self.dimensions if d.counted]

    @property
    def context(self) -> list[Dimension]:
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


# ── Dimensions the renter asked for (counted in the %) ─────────────────────

def _budget(s: _Subject, prefs) -> Dimension | None:
    if not prefs.max_price:
        return None
    budget = float(prefs.max_price)
    eff = s.effective_price
    if eff is None:
        return Dimension('budget', 'Budget', None, 'No price listed', metric=None)
    headroom = budget - eff
    price_txt = ('From ' if s.from_price else '') + _money(eff) + s.per
    if s.bills:
        price_txt += f" after utilities (included, worth ~{_money(UTILITIES_CREDIT)})"
    if headroom >= 0:
        score = 70 + int(round(30 * min(1.0, headroom / (0.3 * budget))))
        evidence = f"{price_txt} · {_money(headroom)} under your {_money(budget)} budget" if headroom >= 25 \
            else f"{price_txt} · right at your {_money(budget)} budget"
    else:
        over = -headroom
        score = max(0, int(round(60 - over / budget * 400)))
        evidence = f"{price_txt} · {_money(over)} over your {_money(budget)} budget"
    return Dimension('budget', 'Budget', score, evidence, metric=eff)


def _bed_label(n: int) -> str:
    return 'Studio' if n == 0 else f"{n} bed"


def _space(s: _Subject, prefs) -> Dimension | None:
    want = prefs.bedrooms
    if want is None:
        return None
    if s.is_community:
        if not s.bedroom_set:
            return Dimension('space', 'Bedrooms', None, 'Floor plans not listed')
        if want in s.bedroom_set:
            return Dimension('space', 'Bedrooms', 100, f"Has {_bed_label(want).lower()} units, as asked")
        if want + 1 in s.bedroom_set:
            return Dimension('space', 'Bedrooms', 70, f"No {_bed_label(want).lower()} units; has {want + 1} bed")
        return Dimension('space', 'Bedrooms', 0, f"No {_bed_label(want).lower()} units")
    have = s.bedrooms
    if have is None:
        return Dimension('space', 'Bedrooms', None, 'Bedrooms not listed')
    if have == want:
        return Dimension('space', 'Bedrooms', 100, f"{_bed_label(have)}, as asked")
    if have == want + 1:
        return Dimension('space', 'Bedrooms', 70, f"{_bed_label(have)}, one more than you asked for")
    if have > want:
        return Dimension('space', 'Bedrooms', 40, f"{_bed_label(have)}, more than you asked for")
    return Dimension('space', 'Bedrooms', 0, f"{_bed_label(have)}; you asked for {_bed_label(want).lower()}")


def _must_haves(s: _Subject, prefs) -> tuple[Dimension | None, list[str], list[str]]:
    if not prefs.tags:
        return None, [], []
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
    parts = [f"{t} ✓" for t in met] + [f"{t} (similar)" for t in near] + [f"{t} ✗" for t in missing]
    dim = Dimension('musthaves', 'Must-haves', score, ' · '.join(parts),
                    metric=len(met) / len(prefs.tags))
    return dim, met, missing


def _move_in(s: _Subject, prefs) -> Dimension | None:
    if not prefs.avail_date or s.is_community:
        return None
    when = s.available_from
    if not when or when <= prefs.avail_date:
        txt = 'Available now' if not when else f"Available {when:%b} {when.day}, before your move-in"
        return Dimension('movein', 'Move-in', 100, txt)
    return Dimension('movein', 'Move-in', 0,
                     f"Available {when:%b} {when.day}, after your {prefs.avail_date:%b} {prefs.avail_date.day} move-in")


# ── Context: facts about the place (never counted in the %) ────────────────

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
        parts.append(f"{link.station.name} ({link.station.get_mode_display().lower()}) {where}")
    score = getattr(item, 'commute_score', None)
    if score is None and minutes:
        score = _falloff(minutes, 15, 60)
    if score is None:
        return Dimension('commute', 'Commute', None, 'No commute data for this address yet', counted=False)
    label = getattr(item, 'commute_score_label', '') or ''
    evidence = ' · '.join(([label] if label else []) + parts) or f"Commute score {score}/100"
    return Dimension('commute', 'Commute', score, evidence, 'Listojo commute score · Google Routes',
                     counted=False, metric=float(minutes) if minutes else None)


def _errands(s: _Subject) -> Dimension:
    stores = [g for g in s.related('nearby_groceries') if g.drive_minutes or g.distance_miles]
    if not stores:
        return Dimension('errands', 'Groceries', None, 'No grocery data for this address yet', counted=False)
    nearest = min(stores, key=lambda g: (g.drive_minutes or 99, float(g.distance_miles or 99)))
    chain = nearest.store.chain or nearest.store.name
    if nearest.drive_minutes:
        return Dimension('errands', 'Groceries', _falloff(nearest.drive_minutes, 5, 25),
                         f"{chain}, {nearest.drive_minutes} min drive", 'Google Places · Google Routes',
                         counted=False, metric=float(nearest.drive_minutes))
    miles = float(nearest.distance_miles)
    return Dimension('errands', 'Groceries', _falloff(miles, 1, 8), f"{chain}, {miles:g} mi",
                     'Google Places', counted=False, metric=miles * 2.5)


def _schools(s: _Subject) -> Dimension | None:
    if s.is_community:
        return None
    rated = [l for l in s.related('nearby_schools') if l.school.rating]
    if not rated:
        return Dimension('schools', 'Schools', None, 'No school ratings for this address yet', counted=False)
    best = max(rated, key=lambda l: (l.school.rating, -float(l.distance_miles or 99)))
    dist = f" · {best.distance_miles} mi" if best.distance_miles is not None else ''
    return Dimension('schools', 'Schools', best.school.rating * 10,
                     f"Best nearby: {best.school.name}, {best.school.rating}/10{dist}", 'GreatSchools',
                     counted=False, metric=float(best.school.rating))


def _walkability(s: _Subject) -> Dimension:
    score = getattr(s.item, 'walk_score', None)
    if score is None:
        return Dimension('walk', 'Walkability', None, 'No walkability data yet', counted=False)
    desc = getattr(s.item, 'walk_score_description', '') or ''
    return Dimension('walk', 'Walkability', score, f"Walk Score {score}" + (f" · {desc}" if desc else ''),
                     'Walk Score', counted=False, metric=float(score))


def _market(s: _Subject) -> Dimension | None:
    """Price against the Listojo price model — detail page only (it loads a model)."""
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
    delta = s.price - estimate
    pct = delta / estimate * 100
    if abs(pct) < 3:
        txt = f"In line with similar homes (Listojo estimate {_money(estimate)})"
    elif delta < 0:
        txt = f"{_money(-delta)} below similar homes (Listojo estimate {_money(estimate)})"
    else:
        txt = f"{_money(delta)} above similar homes (Listojo estimate {_money(estimate)})"
    score = max(0, min(100, int(round(60 - pct * 4))))
    return Dimension('market', 'Price vs market', score, txt, 'Listojo price model', counted=False,
                     metric=pct)


# ── Strengths and the catch ─────────────────────────────────────────────────

def _priority_weight(prefs, key: str) -> int:
    favoured = {
        'price': {'budget'},
        'location': {'commute', 'errands', 'walk'},
        'features': {'musthaves'},
    }.get(getattr(prefs, 'priority', '') or '', set())
    return 3 if key in favoured else 1


def _strengths(dims: dict[str, Dimension], met: list[str], prefs) -> list[_Candidate]:
    out = []

    def add(key, text):
        out.append(_Candidate(key, text, _priority_weight(prefs, key)))

    d = dims.get('budget')
    if d and d.score is not None and d.score >= 80 and d.metric is not None:
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
    if d and d.score is not None and d.score >= 70:
        add('commute', d.evidence.split(' · ')[0])
    d = dims.get('errands')
    if d and d.score is not None and d.score >= 75:
        add('errands', f"Groceries close: {d.evidence}")
    d = dims.get('schools')
    if d and d.score is not None and d.score >= 80:
        add('schools', d.evidence.replace('Best nearby: ', 'Strong school nearby: '))
    d = dims.get('walk')
    if d and d.score is not None and d.score >= 70:
        add('walk', d.evidence)
    d = dims.get('market')
    if d and d.metric is not None and d.metric <= -3:
        add('market', d.evidence)
    return out


def _own_catch(s: _Subject, dims: dict[str, Dimension], missing: list[str], prefs) -> str | None:
    """The most serious downside we can state from this listing's own data."""
    d = dims.get('budget')
    if d and d.score is not None and d.score < 70:
        return d.evidence.split(' · ')[-1].capitalize()
    if missing:
        names = ', '.join(missing[:2])
        return f"No {names} listed" + (f" (+{len(missing) - 2} more)" if len(missing) > 2 else '')
    d = dims.get('space')
    if d and d.score is not None and d.score < 50:
        return d.evidence
    d = dims.get('movein')
    if d and d.score == 0:
        return d.evidence
    d = dims.get('market')
    if d and d.metric is not None and d.metric >= 8:
        return d.evidence
    d = dims.get('errands')
    if d and d.metric is not None and d.metric > 12:
        return f"Nearest groceries are a drive: {d.evidence}"
    d = dims.get('commute')
    if d and d.score is not None and d.score < 40:
        return f"Car-dependent: {d.evidence}"
    d = dims.get('walk')
    if d and d.score is not None and d.score < 25:
        return f"Car-dependent: {d.evidence}"
    d = dims.get('schools')
    if d and d.score is not None and d.score <= 40 and (prefs.bedrooms or 0) >= 3:
        return f"Schools rate low: {d.evidence.replace('Best nearby: ', 'best nearby is ')}"
    return None


# ── Building reports ────────────────────────────────────────────────────────

def _dimensions(s: _Subject, prefs, detail: bool) -> tuple[dict[str, Dimension], list[str], list[str]]:
    dims: dict[str, Dimension] = {}
    for d in (_budget(s, prefs), _space(s, prefs), _move_in(s, prefs)):
        if d:
            dims[d.key] = d
    must, met, missing = _must_haves(s, prefs)
    if must:
        dims[must.key] = must
    for d in (_commute(s), _errands(s), _schools(s), _walkability(s)):
        if d:
            dims[d.key] = d
    if detail:
        d = _market(s)
        if d:
            dims[d.key] = d
    return dims, met, missing


_ORDER = ['budget', 'space', 'musthaves', 'movein', 'commute', 'errands', 'schools', 'walk', 'market']


def _assemble(pct: int, dims, strengths, catch, tone, best_of) -> FitReport:
    ordered = [dims[k] for k in _ORDER if k in dims]
    covered = [d for d in ordered if d.score is not None]
    sources = []
    for d in covered:
        for src in filter(None, (x.strip() for x in d.source.split('·'))):
            if src not in sources:
                sources.append(src)
    band = match_band(pct)
    return FitReport(
        pct=pct, band=band, label=BAND_LABELS[band], dimensions=ordered,
        strengths=strengths, best_of=best_of, catch=catch, catch_tone=tone,
        covered=len(covered), possible=len(ordered), sources=sources,
    )


def _fallback_catch(dims) -> tuple[str, str]:
    context = [d for d in dims.values() if not d.counted]
    if context and all(d.score is None for d in context):
        return 'No commute or neighborhood data for this address yet', 'unknown'
    return 'No red flags in the data we have', 'clear'


def _score(item, prefs):
    from listings.models import Community
    return prefs.score_community(item) if isinstance(item, Community) else prefs.score(item)


def build_report(item, prefs, *, detail: bool = False) -> FitReport | None:
    """One listing on its own — the detail page, where there's no result set to compare to."""
    result = _score(item, prefs)
    if result.pct is None:
        return None
    s = _Subject(item)
    dims, met, missing = _dimensions(s, prefs, detail)
    cands = sorted(_strengths(dims, met, prefs), key=lambda c: -c.weight)
    catch = _own_catch(s, dims, missing, prefs)
    tone = 'bad'
    if not catch:
        catch, tone = _fallback_catch(dims)
    return _assemble(result.pct, dims, [c.text for c in cands[:3]], catch, tone, None)


# Comparisons across a results page: metric key, better = 'low'|'high', phrasing.
_COMPARISONS = {
    'budget': ('low', lambda n, v, gap: f"Cheapest of your {n} matches, {_money(gap)} less than the next"),
    'commute': ('low', lambda n, v, gap: f"Shortest drive to downtown of your {n} matches ({int(v)} min)"),
    'errands': ('low', lambda n, v, gap: f"Closest groceries of your {n} matches"),
    'schools': ('high', lambda n, v, gap: f"Best-rated nearby school of your {n} matches ({int(v)}/10)"),
    'walk': ('high', lambda n, v, gap: f"Most walkable of your {n} matches (Walk Score {int(v)})"),
}


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
        s = _Subject(item)
        dims, met, missing = _dimensions(s, prefs, detail=False)
        rows.append((item, result.pct, s, dims, met, missing))
    if not rows:
        return {}

    n = len(rows)
    # A strength every match shares tells the renter nothing about this one.
    cand_by_pk = {r[0].pk: _strengths(r[3], r[4], prefs) for r in rows}
    shared = set()
    if n >= 2:
        key_sets = [{c.key for c in cands} for cands in cand_by_pk.values()]
        shared = set.intersection(*key_sets)

    # Best-of and relative catches, per comparable dimension.
    best_of: dict = {}
    worst: dict = {}
    for key in _comparison_order(prefs):
        better, phrase = _COMPARISONS[key]
        values = [(r[0].pk, r[3][key].metric) for r in rows
                  if key in r[3] and r[3][key].metric is not None and r[3][key].score is not None]
        if len(values) < MIN_TO_COMPARE:
            continue
        ranked = sorted(values, key=lambda kv: kv[1], reverse=(better == 'high'))
        (top_pk, top_v), (_, next_v) = ranked[0], ranked[1]
        if top_v != next_v and top_pk not in best_of:
            best_of[top_pk] = (key, phrase(len(values), top_v, abs(next_v - top_v)))
        mid = median(v for _, v in values)
        (low_pk, low_v) = ranked[-1]
        if low_pk not in worst and low_v != ranked[-2][1] and mid:
            off = (low_v - mid) / mid if better == 'low' else (mid - low_v) / mid
            if off >= 0.1:
                if key == 'budget':
                    worst[low_pk] = f"Priciest of your {len(values)} matches, {_money(low_v - mid)} above the median"
                elif key == 'commute':
                    worst[low_pk] = f"Longest drive to downtown of your {len(values)} matches ({int(low_v)} min)"
                elif key == 'errands':
                    worst[low_pk] = f"Furthest from groceries of your {len(values)} matches"

    reports = {}
    for item, pct, s, dims, met, missing in rows:
        best = best_of.get(item.pk)
        cands = [c for c in cand_by_pk[item.pk]
                 if c.key not in shared and not (best and c.key == best[0])]
        cands.sort(key=lambda c: -c.weight)
        catch = _own_catch(s, dims, missing, prefs) or worst.get(item.pk)
        tone = 'bad'
        if not catch:
            catch, tone = _fallback_catch(dims)
        reports[item.pk] = _assemble(pct, dims, [c.text for c in cands[:2]], catch, tone,
                                     best[1] if best else None)
    return reports
