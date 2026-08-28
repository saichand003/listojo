"""
Nearest transit stations for a listing.

Usage:
    from listings.services.transit import nearest_stations, sync_instance

    nearest_stations(32.837828, -96.774939)   # → [(TransitStation, 0.4), ...]
    sync_instance(listing)                    # writes ListingTransitStation rows

No API is involved: stations come from the GTFS import (see services.gtfs) and
the distance is local maths, so this is free to recompute. The staleness window
therefore exists only to keep re-runs cheap in *database* terms, not to ration
API calls the way the grocery and school syncs do.

Distances are straight-line, matching services.distance's contract. Drive times
are filled in afterwards by services.drivetime, which folds these rows into the
same Routes matrix call as the downtown and the groceries.
"""
from __future__ import annotations

import logging
from datetime import timedelta

from django.core.cache import cache
from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from listings.services.distance import bounding_box, haversine_miles

logger = logging.getLogger(__name__)

# Stations move on the order of years, and the import command is what actually
# refreshes them; this only decides how often a listing re-measures against the
# table. Matches the 180 days used by the grocery and drive-time syncs.
STALE_AFTER = timedelta(days=180)

# Beyond this a station stops being a fact about the listing. Five miles is
# generous for a rail station you would drive and park at, and far beyond
# walking, which is the point: the card quotes a drive time when it is one.
DEFAULT_RADIUS_MILES = 5.0

# A frequent bus stop is only interesting if you can walk to it, so surface
# modes get a much tighter radius than rail.
SURFACE_RADIUS_MILES = 1.5

# How many of each kind the card shows. Separate limits, not one shared budget:
# the card gives rail and bus their own sections, so a dense listing no longer
# has to choose between showing a third rail station and showing any bus at all.
DEFAULT_RAIL_LIMIT = 3
DEFAULT_SURFACE_LIMIT = 3

def nearest_stations(lat, lng, *, rail_limit: int = DEFAULT_RAIL_LIMIT,
                     surface_limit: int = DEFAULT_SURFACE_LIMIT):
    """
    Return [(TransitStation, miles)] for the closest stations, rail first.

    Rail and surface get independent limits because the card shows them in
    separate sections. An earlier version spent one shared budget of three and
    held a single slot back for surface; that was already a fix for dense
    listings filling every slot with rail, but it still capped a listing at one
    bus stop however many it had.

    Rail is searched to DEFAULT_RADIUS_MILES and surface stops only to
    SURFACE_RADIUS_MILES, since a bus stop you cannot walk to is not a fact
    about the address.

    Distance is compared *within* a group and never across modes. Ranking by
    mode first is wrong by a mile, literally: commuter rail outranks light rail,
    so a listing at SMU/Mockingbird Station matched Victory Station 3.9 miles
    away on the strength of it being TRE, and scored 47 instead of 88.

    Surface stops are ordered by distance alone, not by frequency. A frequent
    stop further away is not more useful than the one outside the door; the card
    prints each stop's headway so the reader can weigh that themselves.

    Returns [] when nothing is in range, which is the normal answer in the parts
    of the footprint no agency serves.
    """
    from listings.models import TransitStation

    if lat is None or lng is None:
        return []

    lat, lng = float(lat), float(lng)
    min_lat, max_lat, min_lng, max_lng = bounding_box(lat, lng, DEFAULT_RADIUS_MILES)

    candidates = (TransitStation.objects
                  .filter(agency__is_active=True,
                          latitude__gte=min_lat, latitude__lte=max_lat,
                          longitude__gte=min_lng, longitude__lte=max_lng)
                  .select_related('agency')
                  # One extra query, and it is what `_distinct_by_route` needs
                  # to compare route sets without a lookup per station.
                  .prefetch_related('routes'))

    rail, surface = [], []
    for station in candidates:
        miles = haversine_miles(lat, lng, station.latitude, station.longitude)
        if miles is None:
            continue
        if station.is_rail:
            if miles <= DEFAULT_RADIUS_MILES:
                rail.append((station, miles))
        elif miles <= SURFACE_RADIUS_MILES:
            surface.append((station, miles))

    rail.sort(key=lambda pair: pair[1])
    surface.sort(key=lambda pair: pair[1])
    return rail[:rail_limit] + _distinct_by_route(surface)[:surface_limit]


def _distinct_by_route(stations):
    """
    Drop a stop when every route it serves is already covered by a nearer one.

    Bus stops are directional and come in pairs, so the two poles at one
    intersection are two rows serving the same route — and a feed names them
    from opposite streets, so they do not even look like duplicates. Valley
    Ranch showed "Luna @ Valley View" and "Valley View @ Luna", both route 227,
    as two of its three bus rows.

    Keeping a stop only when it adds a route guarantees every row earns its
    place. Same spirit as the grocery service showing one branch per chain.

    `stations` must already be sorted nearest-first: the rule keeps whichever
    stop for a route comes first.
    """
    covered, kept = set(), []
    for station, miles in stations:
        routes = {route.pk for route in station.routes.all()}
        if routes and routes <= covered:
            continue
        covered |= routes
        kept.append((station, miles))
    return kept


# How long the newest-import timestamp is memoised for. One query a minute is
# nothing, and it keeps `is_stale` from hitting the database once per listing
# when the command walks the whole table.
_IMPORT_STAMP_KEY = 'transit:last_import'
_IMPORT_STAMP_TTL = 60


def latest_import_at():
    """
    When any active agency's feed was last imported, or None.

    Cached briefly — see _IMPORT_STAMP_TTL.
    """
    from listings.models import TransitAgency

    cached = cache.get(_IMPORT_STAMP_KEY, 'miss')
    if cached != 'miss':
        return cached

    stamp = (TransitAgency.objects.filter(is_active=True)
             .aggregate(latest=Max('last_imported'))['latest'])
    cache.set(_IMPORT_STAMP_KEY, stamp, _IMPORT_STAMP_TTL)
    return stamp


def is_stale(instance) -> bool:
    """
    True when the instance has never been matched, its match aged out, or the
    station table has been re-imported since.

    That last clause matters more than the age one. Stations only move when a
    feed is re-imported, so a match from before the newest import is out of date
    however recent it is — and without this the symptom is silent: `fetch_transit`
    reports "0 candidate rows", exits successfully, and the card keeps showing
    the old set. That happened twice in a row on the same listing, once when
    relaxing which stops get imported made bus stops appear near it and the
    listing went on showing none.
    """
    if instance.transit_updated is None:
        return True
    if timezone.now() - instance.transit_updated > STALE_AFTER:
        return True

    imported = latest_import_at()
    return imported is not None and instance.transit_updated < imported


def sync_instance(instance, *, force: bool = False) -> int | None:
    """
    Match a Listing to its nearest stations and write the link rows. Saves.

    Returns how many stations were linked, or None when nothing was attempted.
    Zero is a real answer: a listing outside every agency's reach has no
    stations, and the timestamp is still stamped so it is not re-scanned on
    every run.

    Stale links are deleted rather than left in place, so a listing whose
    address changed does not keep a station from its old neighbourhood. Drive
    figures are not preserved across a re-match: they belong to a listing-station
    pair, and services.drivetime refills them on its own schedule.
    """
    from listings.models import CommunityTransitStation, ListingTransitStation

    link_model, owner_field = ((CommunityTransitStation, 'community')
                               if instance._meta.model_name == 'community'
                               else (ListingTransitStation, 'listing'))

    if instance.latitude is None or instance.longitude is None:
        return None
    if not force and not is_stale(instance):
        return None

    matches = nearest_stations(instance.latitude, instance.longitude)
    keep_ids = {station.pk for station, _ in matches}

    with transaction.atomic():
        instance.nearby_transit.exclude(station_id__in=keep_ids).delete()

        for station, miles in matches:
            link_model.objects.update_or_create(
                **{owner_field: instance}, station=station,
                defaults={'distance_miles': round(miles, 1)},
            )

        instance.transit_updated = timezone.now()
        instance.save(update_fields=['transit_updated'])

    return len(matches)
