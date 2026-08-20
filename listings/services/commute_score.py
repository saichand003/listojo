"""
The Commute Score — Listojo's 0-100 measure of how well a listing is connected.

Usage:
    from listings.services.commute_score import score_listing, assign_instance

    score_listing(listing)     # → ScoreResult(score=78, label='Excellent Transit', ...)
    assign_instance(listing)   # stamps the model in-place (no save)

Why we compute our own rather than showing Walk Score's Transit Score
---------------------------------------------------------------------
Walk Score's number is still fetched and stored (services.walkscore), but it is
no longer displayed — see Listing.walk_score_rows. Two transit numbers side by
side invite a comparison that neither wins, and this one answers the question a
renter is actually asking on a Listojo listing: can I get to work from here.
It is built from the three things we can state plainly under the dial —
which line, how far, how long to downtown — where the licensed score is a black
box we cannot explain when someone disagrees with it.

Reading the weights
-------------------
Three components summing to 100:

    Transit access   55   distance to the best station, scaled by its mode
    Network reach    25   how many distinct frequent routes are within reach
    Downtown drive   20   typical no-traffic drive to the nearest downtown

Downtown drive is held at 20 deliberately, and that number is load-bearing. It
is the one component a listing can earn with no transit whatsoever — it measures
a *car* commute — so its ceiling is also the ceiling for an address with nothing
in range. At 20 that address tops out inside "Car-Dependent", which is the
honest label. Raising it to 25 in an early cut pushed those addresses onto the
"Some Transit" floor, which claims a bus stop that is not there. If the bands or
this weight are ever changed, keep DOWNTOWN_POINTS below the "Some Transit"
floor in SCORE_BANDS.

An earlier cut scored rail and bus as separate components, with rail worth 45
and bus worth 15. That was wrong in a way worth recording: because network reach
also counted rail lines only, 65 of the 100 points were unreachable without
rail, so a bus-only address was capped at 35 however good its service was. A
corner in Oak Cliff with three frequent routes and a twelve-minute drive
downtown was permanently "Some Transit". The score was really answering "is
there rail here" and calling itself a commute score.

So access is now one component scored on whichever station is *best*, where
"best" already accounts for mode:

  * A bus stop earns 60% of what a rail station at the same distance earns
    (MODE_ACCESS_FACTOR), and a stop short of the frequency threshold is
    discounted again (INFREQUENT_SERVICE_FACTOR). Rail is still worth more — it
    is faster, it is not stuck in the traffic you are trying to avoid, and it is
    what most renters are actually choosing the address for — but the difference
    is a discount, not a wall.
  * For network reach, a frequent bus route counts as half a rail line. Four
    frequent bus routes are a real network; they are not four rail lines.

A well-served bus-only address now tops out around 79 — "Excellent Transit" —
while a rail interchange still reaches 100.

Every component degrades linearly from a flat top to a hard zero. Linear was
chosen over a decay curve because the whole point is to be explainable: "half a
mile costs you nine points" is a sentence you can put in front of a user, and an
exponent is not.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from listings.services.distance import bounding_box, haversine_miles

logger = logging.getLogger(__name__)

# (points, full_within, zero_at) per component. `full_within` earns the whole
# allocation; the score falls linearly to nothing at `zero_at`.
ACCESS_POINTS = 55.0
# Rail is worth walking or driving further to, so it keeps a generous radius.
RAIL_FULL_MI, RAIL_ZERO_MI = 0.5, 5.0
# A bus stop only counts if you could walk to it, hence the much tighter band.
SURFACE_FULL_MI, SURFACE_ZERO_MI = 0.25, 1.5

DOWNTOWN_POINTS, DOWNTOWN_FULL_MIN, DOWNTOWN_ZERO_MIN = 20.0, 10.0, 60.0

# What a station's mode is worth as a fraction of the access allocation. A bus
# at the door is genuinely useful; it is not a train at the door.
MODE_ACCESS_FACTOR = {
    'commuter_rail': 1.0,
    'subway':        1.0,
    'light_rail':    1.0,
    'streetcar':     0.8,
    'bus':           0.6,
}

# Applied on top of the mode factor when a surface stop falls short of
# FREQUENT_TRIPS_PER_WEEKDAY.
#
# This exists because the card now shows every bus stop with weekday service,
# not only the frequent ones — see services.gtfs. Showing a stop and rewarding
# it are separate decisions: without this discount, a listing beside a
# twice-an-hour circulator would score like one beside a route running every ten
# minutes, and the whole point of weighting bus at 0.6 would be lost. A stop you
# have to plan your day around is worth something, but not that.
INFREQUENT_SERVICE_FACTOR = 0.55

# Line-equivalents reachable → points. Flattens fast on purpose: the second line
# is worth far more than the fourth, because it is the one that turns a single
# commute into a network.
REACH_POINTS = {0: 0.0, 1: 12.0, 2: 19.0, 3: 22.0}
REACH_MAX = 25.0

# A frequent bus route is half a rail line for reach purposes. Four frequent
# routes are a real network; they are not four rail lines.
BUS_LINE_EQUIVALENT = 0.5

# How far out a rail line still counts toward reach. Wider than walking distance
# because these are lines you would drive to a park-and-ride for, which is how
# most of this metro uses rail. Bus routes use the walkable radius instead —
# nobody drives to a bus stop.
REACH_RADIUS_MILES = 3.0
SURFACE_REACH_RADIUS_MILES = 1.5

# Descending; the first band a score clears wins.
SCORE_BANDS = (
    (90, 'Exceptional Transit'),
    (70, 'Excellent Transit'),
    (50, 'Good Transit'),
    (25, 'Some Transit'),
    (0,  'Car-Dependent'),
)


@dataclass
class ScoreResult:
    """A score, its band, and the component breakdown behind it."""

    score: int
    label: str
    components: dict = field(default_factory=dict)


def _falloff(value, full_within: float, zero_at: float, points: float) -> float:
    """
    Full points up to `full_within`, nothing from `zero_at`, linear between.

    None scores zero rather than raising: an unmeasured component is a listing
    with nothing nearby, which is a real answer worth zero points, not an error.
    """
    if value is None:
        return 0.0
    value = float(value)
    if value <= full_within:
        return points
    if value >= zero_at:
        return 0.0
    return points * (zero_at - value) / (zero_at - full_within)


def _access_points(link) -> float:
    """
    What one nearby station is worth, before comparing it with the others.

    Rail and surface stops are measured on different distance bands and then
    scaled by mode, so a bus stop at the door and a rail station a mile off can
    be compared on one number — which is what lets the caller simply take the
    best.
    """
    if link.distance_miles is None:
        return 0.0

    station = link.station
    if station.is_rail:
        full, zero = RAIL_FULL_MI, RAIL_ZERO_MI
    else:
        full, zero = SURFACE_FULL_MI, SURFACE_ZERO_MI

    factor = MODE_ACCESS_FACTOR.get(station.mode, MODE_ACCESS_FACTOR['bus'])
    if not station.is_rail and not station.is_frequent:
        factor *= INFREQUENT_SERVICE_FACTOR

    return _falloff(link.distance_miles, full, zero, ACCESS_POINTS) * factor


def _line_equivalents_within(lat, lng) -> float:
    """
    Distinct frequent routes near a point, counting a bus route as half a line.

    Counts routes, not stations: two stations on the same Red Line are one line
    to a commuter, and rewarding them twice would score a listing strung along a
    single corridor above one at a genuine interchange.

    Bus routes must be flagged frequent in their own right. A stop can clear the
    frequency threshold on the sum of several thin routes, and none of those is
    a route you would plan a commute around.
    """
    from listings.models import RAIL_MODES, TransitStation

    lat, lng = float(lat), float(lng)
    # One box at the wider radius; each station is then held to its own ceiling.
    min_lat, max_lat, min_lng, max_lng = bounding_box(lat, lng, REACH_RADIUS_MILES)
    nearby = (TransitStation.objects
              .filter(agency__is_active=True,
                      latitude__gte=min_lat, latitude__lte=max_lat,
                      longitude__gte=min_lng, longitude__lte=max_lng)
              .prefetch_related('routes'))

    rail_lines, bus_routes = set(), set()
    for station in nearby:
        actual = haversine_miles(lat, lng, station.latitude, station.longitude)
        if actual is None:
            continue
        ceiling = (REACH_RADIUS_MILES if station.is_rail
                   else SURFACE_REACH_RADIUS_MILES)
        if actual > ceiling:
            continue
        for route in station.routes.all():
            if route.mode in RAIL_MODES:
                rail_lines.add(route.pk)
            elif route.is_frequent:
                bus_routes.add(route.pk)

    # A route reachable both ways counts once, on its better footing.
    bus_routes -= rail_lines
    return len(rail_lines) + BUS_LINE_EQUIVALENT * len(bus_routes)


def band_for(score: int) -> str:
    """The band name for a score."""
    for floor, label in SCORE_BANDS:
        if score >= floor:
            return label
    return SCORE_BANDS[-1][1]


def score_listing(listing) -> ScoreResult | None:
    """
    Compute the Commute Score for a Listing, or None if it cannot be scored.

    None means "we do not know" and must not be stored as a zero: an ungeocoded
    listing, or one whose stations have never been matched, has no evidence
    either way, and a hard zero on the card would read as a claim we cannot
    support. A geocoded, matched listing with nothing near it does score zero —
    that is a finding.

    Reads the already-matched `nearby_transit` rows rather than re-running the
    proximity search, so this is cheap enough to recompute on demand. Run
    services.transit.sync_instance first.
    """
    if listing.latitude is None or listing.longitude is None:
        return None
    if listing.transit_updated is None:
        return None

    links = list(listing.nearby_transit.select_related('station'))

    # The best station wins outright, whatever its mode — see the module notes.
    access = max((_access_points(link) for link in links), default=0.0)

    # Only pay for the reach query when something is actually in range.
    equivalents = _line_equivalents_within(listing.latitude,
                                           listing.longitude) if links else 0.0
    # The ladder is defined on whole lines; half-lines round down to the rung
    # they have actually cleared.
    reach = REACH_POINTS.get(int(equivalents), REACH_MAX)

    components = {
        'transit_access': access,
        'network_reach': reach,
        'downtown_drive': _falloff(listing.downtown_drive_minutes,
                                   DOWNTOWN_FULL_MIN, DOWNTOWN_ZERO_MIN,
                                   DOWNTOWN_POINTS),
    }

    total = int(round(min(100.0, sum(components.values()))))
    return ScoreResult(score=total, label=band_for(total),
                       components={k: round(v, 1) for k, v in components.items()})


def assign_instance(listing) -> int | None:
    """
    Set commute_score / commute_score_label on a Listing (does NOT save).

    Returns the score, or None when the listing cannot be scored — in which case
    the fields are cleared, so a listing that loses its geocode stops showing a
    score computed from an address it no longer has.
    """
    result = score_listing(listing)

    if result is None:
        listing.commute_score = None
        listing.commute_score_label = ''
        return None

    listing.commute_score = result.score
    listing.commute_score_label = result.label
    return result.score
