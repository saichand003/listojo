"""
Straight-line distance between two coordinates.

Usage:
    from listings.services.distance import haversine_miles

    haversine_miles(32.914178, -96.964342, 32.7767, -96.7970)  # → 17.3

Used by the downtown and grocery features. Both quote "as the crow flies"
distance, not driving distance: driving distance would need a Directions API
call per pair, which is a per-render cost for a number renters read as a rough
proximity cue anyway. If driving time is ever wanted, it belongs in its own
service — do not quietly redefine what this returns.
"""
from __future__ import annotations

from math import asin, cos, radians, sin, sqrt

# Mean Earth radius. Miles because every consumer-facing distance on the site
# is in miles (the schools card included).
_EARTH_RADIUS_MILES = 3958.7613


def haversine_miles(lat1, lng1, lat2, lng2) -> float | None:
    """
    Great-circle distance in miles, or None if any coordinate is missing.

    Returns None rather than raising so callers can pass model fields straight
    in — an ungeocoded row is a normal state here, not an error.
    """
    if lat1 is None or lng1 is None or lat2 is None or lng2 is None:
        return None

    lat1, lng1, lat2, lng2 = (radians(float(v)) for v in (lat1, lng1, lat2, lng2))

    dlat = lat2 - lat1
    dlng = lng2 - lng1
    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlng / 2) ** 2
    return 2 * _EARTH_RADIUS_MILES * asin(sqrt(a))
