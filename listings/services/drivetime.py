"""
Google Routes — typical driving time from a listing to its nearby places.

Usage:
    from listings.services.drivetime import sync_instance

    sync_instance(listing)   # one API call: time AND road distance for
                             # the downtown and every grocery row

One call, not one per destination
---------------------------------
`computeRouteMatrix` takes one origin against many destinations in a single
request, so a listing's downtown and all its grocery stores are priced as ~6
billable *elements* inside **one** HTTP call. Issuing a separate call per
destination — the obvious approach — costs the same in elements but multiplies
request overhead and rate-limit pressure for nothing.

Traffic
-------
Deliberately TRAFFIC_UNAWARE. Two reasons: it is the Essentials SKU with the
larger free allowance, and these times are computed at sync time and stored, so
a traffic-aware number would be a rush-hour reading shown at midnight (or the
reverse). What we store is a stable "typical drive", which is what a listing
page should claim. Do not switch this to TRAFFIC_AWARE without also moving the
computation to render time — and that would put an API call on every page view,
which is the one thing the whole design exists to avoid.

Results arrive out of order
---------------------------
The matrix response is a stream: elements come back in whatever order the
service finishes them, so `originIndex` / `destinationIndex` are the only safe
way to line answers up with what was asked. Never zip by position.
"""
from __future__ import annotations

import logging
from datetime import timedelta

import requests
from django.conf import settings
from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)

_MATRIX_URL = 'https://routes.googleapis.com/distanceMatrix/v2:computeRouteMatrix'
_TIMEOUT = 12  # seconds — a matrix is slower than a single lookup

# Roads change far more slowly than shop openings, so this can be generous.
STALE_AFTER = timedelta(days=180)

# computeRouteMatrix caps a TRAFFIC_UNAWARE request at 625 elements. We send one
# origin against a handful of destinations, so this is a guard, not a limit we
# expect to reach.
_MAX_DESTINATIONS = 100

# Only a route the service could actually solve carries a usable duration.
_ROUTE_EXISTS = 'ROUTE_EXISTS'


def _waypoint(lat, lng):
    return {'waypoint': {'location': {'latLng': {
        'latitude': float(lat), 'longitude': float(lng)}}}}


def _minutes(duration) -> int | None:
    """
    Convert a protobuf duration ('300s') to whole minutes, rounded up.

    Rounded up because a 90-second hop reading as "1 min" is friendlier than
    "2 min", but a 30-second one reading as "0 min" is nonsense.
    """
    if not duration:
        return None
    try:
        seconds = float(str(duration).rstrip('s'))
    except (TypeError, ValueError):
        return None
    if seconds <= 0:
        return None
    return max(1, int(seconds / 60 + 0.5))


_METRES_PER_MILE = 1609.344


def _miles(metres) -> float | None:
    """Convert route distance in metres to miles, at the precision we display."""
    try:
        return round(float(metres) / _METRES_PER_MILE, 1)
    except (TypeError, ValueError):
        return None


def fetch_drive_matrix(origin, destinations) -> dict[int, dict] | None:
    """
    Drive time and road distance from one origin to many destinations, in one call.

    `origin` and each destination are (lat, lng) pairs. Returns a dict keyed by
    the destination's index in the input list, each value {'minutes', 'miles'} —
    destinations with no drivable route are simply absent — or None if the whole
    call failed.

    None means the lookup failed; an empty dict means it worked and nothing was
    reachable. Callers must not treat them alike, or an outage would wipe stored
    times off every listing it touched.
    """
    api_key = (getattr(settings, 'GOOGLE_ROUTES_API_KEY', '')
               or getattr(settings, 'GOOGLE_PLACES_API_KEY', '')
               or getattr(settings, 'GOOGLE_GEOCODING_API_KEY', '')
               or getattr(settings, 'GOOGLE_MAPS_API_KEY', ''))
    if not api_key:
        logger.warning('fetch_drive_matrix: no Google Routes key set — skipping')
        return None

    if not destinations or origin[0] is None or origin[1] is None:
        return None

    usable = [(i, d) for i, d in enumerate(destinations)
              if d[0] is not None and d[1] is not None][:_MAX_DESTINATIONS]
    if not usable:
        return None

    try:
        resp = requests.post(
            _MATRIX_URL,
            json={
                'origins': [_waypoint(*origin)],
                'destinations': [_waypoint(*d) for _, d in usable],
                'travelMode': 'DRIVE',
                'routingPreference': 'TRAFFIC_UNAWARE',
            },
            headers={
                'Content-Type': 'application/json',
                'X-Goog-Api-Key': api_key,
                # Routes bills by the fields requested. `condition` is needed to
                # tell "10 minutes away" from "no route found".
                # distanceMeters rides along on an element we are already
                # paying for, so road distance costs nothing extra.
                'X-Goog-FieldMask': ('originIndex,destinationIndex,duration,'
                                     'distanceMeters,condition'),
            },
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
    except (requests.RequestException, ValueError) as exc:
        logger.warning('fetch_drive_matrix: request failed for %s: %s', origin, exc)
        return None

    if not isinstance(data, list):
        logger.warning('fetch_drive_matrix: unexpected payload shape for %s', origin)
        return None

    out = {}
    for element in data:
        if not isinstance(element, dict):
            continue
        if element.get('condition') != _ROUTE_EXISTS:
            continue
        minutes = _minutes(element.get('duration'))
        if minutes is None:
            continue
        # Map back through the caller's indexes — see the module docstring.
        matrix_index = element.get('destinationIndex')
        if matrix_index is None or matrix_index >= len(usable):
            continue
        out[usable[matrix_index][0]] = {
            'minutes': minutes,
            'miles': _miles(element.get('distanceMeters')),
        }

    return out


def is_stale(instance) -> bool:
    """True when the instance has never been synced, or its times aged out."""
    if instance.drive_times_updated is None:
        return True
    return timezone.now() - instance.drive_times_updated > STALE_AFTER


def sync_instance(instance, *, force: bool = False) -> int | None:
    """
    Fill drive time and road distance for a Listing's downtown and grocery
    rows, in one call.

    Returns how many times were written, or None when nothing was attempted or
    the call failed. Saves, like the other proximity syncs.

    Run this *after* assign_downtowns and fetch_groceries — it fills in times
    for whatever those two have already matched, and has nothing to do if they
    have not run.
    """
    if instance.latitude is None or instance.longitude is None:
        return None
    if not force and not is_stale(instance):
        return None

    origin = (instance.latitude, instance.longitude)

    # Index 0 is reserved for the downtown when there is one, so the response
    # can be split back apart without a second lookup.
    targets = []
    downtown = instance.nearest_downtown
    if downtown is not None:
        targets.append((downtown.latitude, downtown.longitude))
    downtown_slot = 0 if downtown is not None else None

    links = list(instance.nearby_groceries.select_related('store'))
    link_slots = {}
    for link in links:
        link_slots[len(targets)] = link
        targets.append((link.store.latitude, link.store.longitude))

    if not targets:
        return None

    results = fetch_drive_matrix(origin, targets)
    if results is None:
        return None

    written = 0
    with transaction.atomic():
        if downtown_slot is not None:
            found = results.get(downtown_slot) or {}
            instance.downtown_drive_minutes = found.get('minutes')
            instance.downtown_drive_miles = found.get('miles')
            written += instance.downtown_drive_minutes is not None

        for slot, link in link_slots.items():
            found = results.get(slot) or {}
            link.drive_minutes = found.get('minutes')
            link.drive_miles = found.get('miles')
            written += link.drive_minutes is not None

        if link_slots:
            type(links[0]).objects.bulk_update(links, ['drive_minutes', 'drive_miles'])

        instance.drive_times_updated = timezone.now()
        # Explicit field list: never re-save the whole row here, or the pre_save
        # geocoding signal would fire for nothing.
        instance.save(update_fields=['downtown_drive_minutes', 'downtown_drive_miles',
                                     'drive_times_updated'])

    return written
