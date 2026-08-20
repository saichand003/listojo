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

from django.db import transaction
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

# How many stations the card shows. Three is enough to say "two lines and a bus"
# without the card turning into a timetable.
DEFAULT_LIMIT = 3

def nearest_stations(lat, lng, *, limit: int = DEFAULT_LIMIT):
    """
    Return [(TransitStation, miles)] for the closest stations, best first.

    Rail comes before surface, and within each group the nearest wins. Rail is
    searched to DEFAULT_RADIUS_MILES and surface stops only to
    SURFACE_RADIUS_MILES.

    One slot is held for the nearest surface stop whenever there is one in
    range, even if that means dropping the furthest rail station. Without the
    reservation, a listing in a dense part of the network fills every slot with
    rail and the card never mentions the bus stop on the corner — and, worse,
    the Commute Score's frequent-service component reads the stored links, so it
    scored zero in exactly the neighbourhoods that earn it.

    Distance is compared *within* a group and never across modes. Ranking by
    mode first is wrong by a mile, literally: commuter rail outranks light rail,
    so a listing at SMU/Mockingbird Station matched Victory Station 3.9 miles
    away on the strength of it being TRE, and scored 47 instead of 88.

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
                  .select_related('agency'))

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

    # Hold back one slot for surface when both kinds are available.
    rail_slots = limit - 1 if (surface and len(rail) >= limit) else limit
    chosen = rail[:rail_slots]
    return chosen + surface[:limit - len(chosen)]


def is_stale(instance) -> bool:
    """True when the instance has never been matched, or its match aged out."""
    if instance.transit_updated is None:
        return True
    return timezone.now() - instance.transit_updated > STALE_AFTER


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
    from listings.models import ListingTransitStation

    if instance.latitude is None or instance.longitude is None:
        return None
    if not force and not is_stale(instance):
        return None

    matches = nearest_stations(instance.latitude, instance.longitude)
    keep_ids = {station.pk for station, _ in matches}

    with transaction.atomic():
        instance.nearby_transit.exclude(station_id__in=keep_ids).delete()

        for station, miles in matches:
            ListingTransitStation.objects.update_or_create(
                listing=instance, station=station,
                defaults={'distance_miles': round(miles, 1)},
            )

        instance.transit_updated = timezone.now()
        instance.save(update_fields=['transit_updated'])

    return len(matches)
