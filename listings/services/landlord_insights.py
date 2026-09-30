"""
What the Fit Report means for the landlord: the other half of the USP.

Renters see how a home fits them (listings.services.fit). Landlords see two
things built from the same facts:

- **Listing strength**: the gaps a landlord can fix in minutes (photos, a
  description, square footage, amenities, the street address). Renters are
  never shown these as flaws; the landlord is shown them as next steps.
- **Renter demand**: what renters who looked at the listing were searching
  for. "7 of 12 renters who viewed wanted in-unit laundry, which you don't
  list" is something no listing site tells a small landlord.

Demand is only reported once at least MIN_RENTERS renters with stated
preferences have viewed the listing, and a line is only shown when at least
MIN_PER_LINE of them share it. Below that the numbers mean nothing and could
point at a single person.
"""
from __future__ import annotations

from dataclasses import dataclass, field

MIN_RENTERS = 10
MIN_PER_LINE = 3

# Event types that mean a renter looked at the listing.
_VIEW_EVENTS = ('click', 'save', 'contact')


# ── Listing strength ────────────────────────────────────────────────────────

@dataclass
class Check:
    key: str
    action: str     # what to do, as a button would say it
    why: str        # why renters care, in one line
    done: bool


@dataclass
class Strength:
    checks: list[Check]

    @property
    def pct(self) -> int:
        return int(round(100 * sum(c.done for c in self.checks) / len(self.checks))) if self.checks else 100

    @property
    def todo(self) -> list[Check]:
        return [c for c in self.checks if not c.done]

    @property
    def next_step(self) -> Check | None:
        return next(iter(self.todo), None)


MIN_PHOTOS = 5
MIN_DESCRIPTION = 150
MIN_AMENITIES = 3


def _photo_action(have: int) -> str:
    if have == 0:
        return f"Add photos (aim for {MIN_PHOTOS})"
    more = MIN_PHOTOS - have
    return f"Add {more} more photo{'s' if more != 1 else ''}" if more > 0 else 'Photos'


def listing_strength(listing) -> Strength:
    photos = len(listing.images.all())
    tags = listing.get_tags_list()
    return Strength([
        Check('photos', _photo_action(photos),
              "Renters decide whether to open a listing from its photos.", photos >= MIN_PHOTOS),
        Check('amenities', 'List your amenities',
              "Renters search by must-haves; one you don't list shows as not listed on their match.",
              len(tags) >= MIN_AMENITIES),
        Check('address', 'Add the full street address',
              "Lets renters see commute, grocery and school facts for your home.",
              listing.latitude is not None),
        Check('sqft', 'Add square footage',
              "Renters compare space and price per square foot between homes.",
              bool(listing.square_footage)),
        Check('description', 'Write a fuller description',
              "Tells renters what photos can't: the street, the light, the building.",
              len((listing.description or '').strip()) >= MIN_DESCRIPTION),
    ])


def community_strength(community) -> Strength:
    photos = len(community.images.all())
    return Strength([
        Check('photos', _photo_action(photos), "Renters decide whether to open a listing from its photos.",
              photos >= MIN_PHOTOS),
        Check('units', 'Mark units as available',
              "Renters filter by bedrooms and move-in; available units are what they can match.",
              bool(community.available_unit_count)),
        Check('amenities', 'List community and in-unit amenities',
              "Renters search by must-haves; one you don't list shows as not listed on their match.",
              bool((community.community_amenities or '').strip() or (community.in_unit_amenities or '').strip())),
        Check('policies', 'Add pet and parking policies',
              "Pet-friendly and parking are among the most-asked must-haves.",
              bool((community.pet_policy or '').strip() and (community.parking_info or '').strip())),
        Check('address', 'Add the full street address',
              "Lets renters see commute and grocery facts for your community.",
              community.latitude is not None),
    ])


# ── Renter demand ───────────────────────────────────────────────────────────

@dataclass
class Demand:
    renters: int                                     # renters with stated preferences who viewed
    ready: bool
    unmet: list[str] = field(default_factory=list)   # wanted, not listed
    met: list[str] = field(default_factory=list)     # wanted, and you list it
    budget_note: str | None = None

    @property
    def still_needed(self) -> int:
        return max(0, MIN_RENTERS - self.renters)


def _viewer_wants(events) -> list[dict]:
    """The latest stated preferences per renter (by account, else by session)."""
    latest: dict[str, dict] = {}
    for ev in events:  # newest first (model ordering)
        who = f"u{ev.user_id}" if ev.user_id else f"s{ev.session_key}"
        if not ev.session_key and not ev.user_id:
            continue
        snap = ev.user_features_snapshot or {}
        if who in latest or not any(snap.get(k) for k in ('max_price', 'max_budget', 'bedrooms', 'tags', 'amenities')):
            continue
        latest[who] = snap
    return list(latest.values())


def _tags(snap: dict) -> list[str]:
    raw = snap.get('tags') or snap.get('amenities') or ''
    return [t.strip().lower() for t in str(raw).split(',') if t.strip()]


def _budget(snap: dict) -> float | None:
    for key in ('max_price', 'max_budget'):
        try:
            v = float(str(snap.get(key) or '').replace('$', '').replace(',', ''))
            if v > 0:
                return v
        except ValueError:
            pass
    return None


def renter_demand(item) -> Demand:
    from listings.models import Community, UserListingEvent
    from listings.services.fit import _Subject
    from listings.services.matching import _TAG_RELATED

    is_community = isinstance(item, Community)
    events = UserListingEvent.objects.filter(
        **({'community': item} if is_community else {'listing': item}),
        event_type__in=_VIEW_EVENTS,
    ).only('user_id', 'session_key', 'user_features_snapshot')
    wants = _viewer_wants(events)
    n = len(wants)
    if n < MIN_RENTERS:
        return Demand(renters=n, ready=False)

    subject = _Subject(item)
    counts: dict[str, int] = {}
    for snap in wants:
        for tag in set(_tags(snap)):
            counts[tag] = counts.get(tag, 0) + 1

    def listed(tag):
        return tag in subject.blob or any(r in subject.blob for r in _TAG_RELATED.get(tag, []))

    ranked = sorted(counts.items(), key=lambda kv: -kv[1])
    unmet = [f"{c} of {n} wanted {t}, which you don't list" for t, c in ranked
             if c >= MIN_PER_LINE and not listed(t)][:3]
    met = [f"{c} of {n} wanted {t}, and you list it" for t, c in ranked
           if c >= MIN_PER_LINE and listed(t)][:3]

    budget_note = None
    if subject.price:
        under = sum(1 for s in wants if (b := _budget(s)) is not None and b < subject.price)
        if under >= MIN_PER_LINE:
            budget_note = (f"{under} of {n} had a budget below your "
                           f"{'starting ' if subject.from_price else ''}price of ${int(subject.price):,}")
    return Demand(renters=n, ready=True, unmet=unmet, met=met, budget_note=budget_note)
