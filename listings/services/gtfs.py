"""
GTFS feed parsing — routes and stations from an agency's published zip.

Usage:
    from listings.services.gtfs import load_feed

    feed = load_feed('https://www.dart.org/transitdata/latest/google_transit.zip')
    feed.routes      # → [RouteRecord, ...]
    feed.stations    # → [StationRecord, ...]  (rail + frequent stops only)

Why GTFS rather than a Places search
------------------------------------
Every consumer of this module could have been a `places:searchNearby` call for
`light_rail_station`, matching how services.groceries works. GTFS was chosen
instead for three reasons, in order of weight:

1. It costs nothing, and nothing per listing. Agencies publish the zip under an
   open licence. The overriding constraint on the proximity features is that
   API spend must not scale with listing volume; this feature has no API spend
   at all, and one import serves every listing in the metro forever.
2. It carries the line. Places returns "Mockingbird Station" and no hint that
   the Red, Blue and Orange lines call there. The badges on the card, and the
   network-reach term in the Commute Score, are only possible from the feed.
3. It carries frequency. Nothing in Places distinguishes a bus stop with four
   buses an hour from one with four a day, and that distinction is the entire
   reason the card is readable — see FREQUENT_TRIPS_PER_WEEKDAY.

This module does no database work and imports no models: it turns a URL into
plain records. Persisting them is the import command's job, which keeps the
parsing testable against a fixture zip with no database at all.
"""
from __future__ import annotations

import csv
import io
import logging
import re
import zipfile
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date

import requests

logger = logging.getLogger(__name__)

_TIMEOUT = 120  # seconds — these are 8-15 MB zips, not API responses
_MAX_ZIP_BYTES = 250 * 1024 * 1024  # refuse a feed large enough to exhaust memory

# A stop qualifies as "frequent" at 60 trips on its busiest weekday.
#
# Bus stops are directional, so a stop sees one direction of a route. Sixty
# trips over a SERVICE_SPAN_HOURS day is a bus roughly every 15 minutes, which
# is the usual threshold for service you can turn up to without consulting a
# timetable. Against DART's feed, 1,634 of 6,837 stops clear it.
#
# This is now a *label*, not a filter. Every stop with weekday service is
# imported and the flag rides along on the row, because the listing card shows
# rail and bus in separate sections: a bus stop no longer displaces a rail
# station, so there is no longer a reason to hide the ones that fall short.
# Valley Ranch is the case that forced this — its only service is Irving
# circulators 227 and 229 at ~32 trips a day, so a listing there showed no bus
# at all rather than "every ~25 min", which is the more useful thing to say.
#
# The distinction still does real work: services.commute_score discounts a
# non-frequent stop heavily, and network reach ignores non-frequent bus routes
# outright. Showing a stop and rewarding it are different decisions.
FREQUENT_TRIPS_PER_WEEKDAY = 60

# Assumed span of a weekday service day, used only to turn a trip count into a
# human headway ("every ~25 min"). Approximate by nature: a stop's real first
# and last departure vary, and the label is rounded to five minutes to avoid
# implying a precision the arithmetic does not have.
SERVICE_SPAN_HOURS = 14

# Non-passenger points that appear in stops.txt because trips are timed through
# them. Left in, they would show up as stations nobody can board at: DART's feed
# has 'EAST TEX YARD LIMIT' and 'SHERMAN POCKET TRACK' sitting on the Red Line.
_NON_PASSENGER = re.compile(
    r'\b(yard\s*limit|pocket\s*track|test\s*track|layover|garage|'
    r'maintenance|shop\s*track|storage\s*track|wye|siding)\b',
    re.IGNORECASE,
)

# Trailing "- <direction> - <position>" on a stop name, e.g. the "- S - FS" in
# "LUNA @ VALLEY VIEW - S - FS" (southbound, far side of the intersection).
# 6,460 of DART's 6,976 stops carry one. It tells an operator which pole to
# service and tells a renter nothing, and title-casing turns it into the
# distinctly broken-looking "- S - Fs". The spacing is inconsistent in the feed
# ("- E- NS" appears a dozen times), hence the loose separators.
_STOP_SUFFIX = re.compile(r'\s*-\s*[NSEW]{1,2}\s*-\s*(NS|FS|MB)\s*$', re.IGNORECASE)

_WEEKDAYS = ('monday', 'tuesday', 'wednesday', 'thursday', 'friday')


def _ymd(value: str):
    """Split a GTFS YYYYMMDD date into (year, month, day) ints."""
    if len(value) != 8 or not value.isdigit():
        raise ValueError(f'not a GTFS date: {value!r}')
    return int(value[:4]), int(value[4:6]), int(value[6:8])


@dataclass
class RouteRecord:
    source_id: str
    short_name: str
    long_name: str
    mode: str
    color: str
    text_color: str
    trips_per_weekday: int = 0

    @property
    def is_frequent(self) -> bool:
        return self.trips_per_weekday >= FREQUENT_TRIPS_PER_WEEKDAY


@dataclass
class StationRecord:
    source_id: str
    name: str
    latitude: float
    longitude: float
    mode: str
    is_rail: bool
    trips_per_weekday: int
    route_ids: list[str] = field(default_factory=list)


@dataclass
class FeedRecord:
    agency_name: str = ''
    feed_version: str = ''
    routes: list[RouteRecord] = field(default_factory=list)
    stations: list[StationRecord] = field(default_factory=list)


def _read_csv(zf: zipfile.ZipFile, filename: str):
    """
    Yield rows of a GTFS text file as dicts, or nothing if it is absent.

    GTFS files are UTF-8 and frequently carry a BOM; `utf-8-sig` strips it so
    the first column name is not silently '﻿route_id'. Optional files
    (calendar.txt is optional when calendar_dates.txt carries the schedule) are
    a normal absence, not an error.
    """
    try:
        raw = zf.read(filename)
    except KeyError:
        logger.info('gtfs: %s absent from feed', filename)
        return
    yield from csv.DictReader(io.StringIO(raw.decode('utf-8-sig')))


def _clean(value) -> str:
    return (value or '').strip()


def _hex_color(value) -> str:
    """Six hex digits with no '#', or '' when the feed omits or mangles it."""
    v = _clean(value).lstrip('#').upper()
    return v if re.fullmatch(r'[0-9A-F]{6}', v) else ''


def _title(name: str) -> str:
    """
    Feed names are usually SHOUTED; title-case them for display.

    Names already in mixed case are left alone — an agency that took the
    trouble to write 'CityLine/Bush' knows better than str.title() does.
    Acronyms that title-casing would ruin are restored afterwards.
    """
    name = _clean(name)
    if not name or not name.isupper():
        return name

    out = name.title()
    # str.title() capitalises after any non-letter, so '12TH' becomes '12Th'.
    out = re.sub(r'(?<=\d)(St|Nd|Rd|Th)\b', lambda m: m.group(1).lower(), out)
    # 'MCKINNEY' likewise becomes 'Mckinney'. Restricted to the handful of
    # prefixes that actually take an internal capital, rather than capitalising
    # after every 'Mc', which would wreck 'Mcallen'.
    for scot in ('McKinney', 'McKalla', 'McLeod', 'McCallum', 'McNeil'):
        out = re.sub(rf'\b{scot.title()}\b', scot, out)
    # Word-boundary matched so 'Dfw' becomes 'DFW' but 'Dfwood Lane' would not.
    for acronym in ('DART', 'DFW', 'TRE', 'EBJ', 'LBJ', 'MLK', 'SMU', 'UNT',
                    'UT', 'VA', 'TC', 'CBD', 'NW', 'NE', 'SW', 'SE'):
        out = re.sub(rf'\b{acronym.title()}\b', acronym, out)
    return out


def _weekday_services(zf) -> dict[str, set[str]]:
    """
    service_id sets active on each weekday, from calendar.txt and calendar_dates.txt.

    Both files are read because the spec allows either to carry the schedule
    alone, and agencies genuinely differ. DART publishes calendar.txt but files
    no Monday service in it — Monday arrives as a calendar_dates addition.
    CapMetro ships no calendar.txt whatsoever and specifies every service day as
    an exception. Reading only the former would silently score every CapMetro
    stop at zero trips, which is how this was found.

    Added-service exceptions (exception_type 1) are folded in under the weekday
    their date falls on, but only when the addition is not a holiday running a
    weekend timetable. Removed-service exceptions (type 2) are ignored: they
    mark holidays and one-off cancellations, and "this route does not run on
    Thanksgiving" should not change what we say about a typical Tuesday.

    The holiday guard is not hypothetical. DART's feed adds its *Sunday*
    services on Labor Day, a Monday. Folding those in blindly gives Monday a
    weekday timetable plus a full Sunday one, and since the count below takes
    the busiest weekday, that fabricated day wins — it more than doubled the
    number of stops clearing the frequency threshold. So an addition counts only
    when the service either has no calendar.txt row at all (the feed keeps its
    whole schedule in exceptions) or already runs on some weekday there.
    """
    services = {day: set() for day in _WEEKDAYS}
    # service_id → does calendar.txt run it on any Mon-Fri. Absent from this
    # map means the feed has no calendar.txt row for it.
    weekday_in_calendar = {}

    for row in _read_csv(zf, 'calendar.txt'):
        sid = _clean(row.get('service_id'))
        if not sid:
            continue
        runs_weekday = False
        for day in _WEEKDAYS:
            if _clean(row.get(day)) == '1':
                services[day].add(sid)
                runs_weekday = True
        weekday_in_calendar[sid] = runs_weekday

    for row in _read_csv(zf, 'calendar_dates.txt'):
        sid = _clean(row.get('service_id'))
        if not sid or _clean(row.get('exception_type')) != '1':
            continue
        if not weekday_in_calendar.get(sid, True):
            continue  # a weekend service being run on a holiday
        try:
            weekday = date(*_ymd(_clean(row.get('date')))).weekday()
        except (TypeError, ValueError):
            continue
        if weekday < len(_WEEKDAYS):  # 5 and 6 are the weekend
            services[_WEEKDAYS[weekday]].add(sid)

    return services


def _trip_counts(zf, route_modes: dict[str, str]):
    """
    Count trips per stop and per route on the busiest weekday.

    Returns (stop_counts, route_counts, stop_routes) where the counts are the
    single highest weekday total, not an average and not a sum over the week.

    The busiest weekday is the honest reading of "how often does this run":
    a weekly sum flatters a five-day route over a seven-day one, and an average
    is dragged down by whichever days the agency happens to model separately.
    Feeds routinely split Friday or Monday into their own service_id, and that
    is a modelling artefact, not less service.

    stop_times.txt is the one large file here — DART's is ~800k rows — so it is
    streamed once and reduced as it goes, never held as a list.
    """
    day_services = _weekday_services(zf)

    # trip_id → (route_id, service_id), for the routes we kept.
    trip_meta = {}
    for row in _read_csv(zf, 'trips.txt'):
        rid = _clean(row.get('route_id'))
        if rid in route_modes:
            trip_meta[_clean(row.get('trip_id'))] = (rid, _clean(row.get('service_id')))

    # (stop_id, route_id, service_id) → calls. Keyed this way so the per-day
    # totals below can be re-sliced without a second pass over stop_times.
    tally = Counter()
    stop_routes = defaultdict(set)
    for row in _read_csv(zf, 'stop_times.txt'):
        meta = trip_meta.get(_clean(row.get('trip_id')))
        if meta is None:
            continue
        stop_id = _clean(row.get('stop_id'))
        if not stop_id:
            continue
        route_id, service_id = meta
        tally[(stop_id, route_id, service_id)] += 1
        stop_routes[stop_id].add(route_id)

    stop_day = defaultdict(Counter)   # stop_id → day → calls
    route_day = defaultdict(Counter)  # route_id → day → trips
    for (stop_id, route_id, service_id), n in tally.items():
        for day in _WEEKDAYS:
            if service_id in day_services[day]:
                stop_day[stop_id][day] += n
                route_day[route_id][day] += n

    stop_counts = {s: max(d.values()) for s, d in stop_day.items() if d}
    route_counts = {r: max(d.values()) for r, d in route_day.items() if d}
    return stop_counts, route_counts, stop_routes


def parse_feed(data: bytes) -> FeedRecord | None:
    """
    Turn the bytes of a GTFS zip into a FeedRecord, or None if unreadable.

    Stations kept: every rail stop, plus every surface stop with any weekday
    service. Frequency is recorded on the row rather than used to exclude it —
    see FREQUENT_TRIPS_PER_WEEKDAY.
    """
    from listings.models import GTFS_ROUTE_TYPES, MODE_RANK, RAIL_MODES

    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        logger.warning('gtfs: payload is not a zip')
        return None

    feed = FeedRecord()

    with zf:
        for row in _read_csv(zf, 'agency.txt'):
            feed.agency_name = _clean(row.get('agency_name'))
            break
        for row in _read_csv(zf, 'feed_info.txt'):
            feed.feed_version = _clean(row.get('feed_version'))[:120]
            break

        routes: dict[str, RouteRecord] = {}
        for row in _read_csv(zf, 'routes.txt'):
            rid = _clean(row.get('route_id'))
            try:
                mode = GTFS_ROUTE_TYPES[int(_clean(row.get('route_type')))]
            except (TypeError, ValueError, KeyError):
                # Ferries, funiculars and anything the spec adds later. Skipped
                # rather than defaulted: a mode we cannot badge or weight would
                # be worse on the card than an absence.
                continue
            if not rid:
                continue
            routes[rid] = RouteRecord(
                source_id=rid,
                short_name=_clean(row.get('route_short_name'))[:60],
                long_name=_title(_clean(row.get('route_long_name')))[:200],
                mode=mode,
                color=_hex_color(row.get('route_color')),
                text_color=_hex_color(row.get('route_text_color')),
            )

        if not routes:
            logger.warning('gtfs: feed has no usable routes')
            return None

        route_modes = {rid: r.mode for rid, r in routes.items()}
        stop_counts, route_counts, stop_routes = _trip_counts(zf, route_modes)

        for rid, route in routes.items():
            route.trips_per_weekday = route_counts.get(rid, 0)

        for row in _read_csv(zf, 'stops.txt'):
            stop_id = _clean(row.get('stop_id'))
            serving = stop_routes.get(stop_id)
            if not serving:
                continue

            # A platform whose parent is also in the feed is folded into the
            # parent, so a four-platform station is one row. Feeds that model
            # stations flat (DART is one) have no parent_station column and
            # already publish a single row per station.
            if _clean(row.get('parent_station')):
                continue
            # location_type 1 is a station, 0 or blank a boarding point;
            # 2-4 are entrances, generic nodes and boarding areas, none of
            # which anyone would call a station.
            if _clean(row.get('location_type')) not in ('', '0', '1'):
                continue

            name = _clean(row.get('stop_name'))
            if not name or _NON_PASSENGER.search(name):
                continue
            # Strip before title-casing: the suffix is upper-case in the feed,
            # which is what the case check in `_title` keys on.
            name = _STOP_SUFFIX.sub('', name).strip() or name

            try:
                lat = float(_clean(row.get('stop_lat')))
                lng = float(_clean(row.get('stop_lon')))
            except (TypeError, ValueError):
                continue
            if not (-90 <= lat <= 90) or not (-180 <= lng <= 180):
                continue
            if lat == 0 and lng == 0:
                continue

            mode = min((routes[r].mode for r in serving if r in routes),
                       key=lambda m: MODE_RANK.get(m, 9), default=None)
            if mode is None:
                continue
            is_rail = mode in RAIL_MODES
            trips = stop_counts.get(stop_id, 0)
            # Rail is kept whatever its frequency — a commuter line running
            # eight times a day is still why someone picks the neighbourhood.
            # Surface stops need only some weekday service; a stop with none is
            # a seasonal or on-request point nobody can plan around.
            if not is_rail and trips <= 0:
                continue

            feed.stations.append(StationRecord(
                source_id=stop_id,
                name=_title(name)[:200],
                latitude=lat,
                longitude=lng,
                mode=mode,
                is_rail=is_rail,
                trips_per_weekday=trips,
                route_ids=sorted(serving),
            ))

    # Only routes that actually call somewhere we kept — dropping the rest
    # keeps the route table from filling with lines whose every stop was
    # filtered out.
    kept = {rid for st in feed.stations for rid in st.route_ids}
    feed.routes = [r for rid, r in routes.items() if rid in kept]
    return feed


def load_feed(url: str) -> FeedRecord | None:
    """
    Download and parse an agency's GTFS zip. None on any failure.

    None means the fetch or parse failed and the caller must leave existing
    stations alone — an agency's feed going missing for a day must not empty
    every listing's transit card.
    """
    try:
        resp = requests.get(url, timeout=_TIMEOUT, stream=True)
        resp.raise_for_status()
        chunks, total = [], 0
        for chunk in resp.iter_content(chunk_size=1 << 20):
            total += len(chunk)
            if total > _MAX_ZIP_BYTES:
                logger.warning('gtfs: %s exceeded %d bytes — abandoned',
                               url, _MAX_ZIP_BYTES)
                return None
            chunks.append(chunk)
    except requests.RequestException as exc:
        logger.warning('gtfs: download failed for %s: %s', url, exc)
        return None

    return parse_feed(b''.join(chunks))
