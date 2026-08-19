"""
Nearest downtown for a listing.

Usage:
    from listings.services.downtowns import nearest_downtown, assign_instance

    nearest_downtown(32.914178, -96.964342)   # → (Downtown, 17.3) or None
    assign_instance(listing)                  # stamps the model in-place (no save)

No API is involved. Downtowns are a curated table (see models.Downtown) and the
distance is local maths, so this is free to recompute as often as you like —
unlike the school and grocery syncs, there is no staleness window to respect.

Note that the nearest downtown is frequently NOT the listing's own city. A
listing in Irving is closer to Downtown Dallas than to most things, and that is
the useful answer for someone judging a commute, so the match deliberately
ignores city boundaries.
"""
from __future__ import annotations

import logging

from listings.services.distance import haversine_miles

logger = logging.getLogger(__name__)


def nearest_downtown(lat, lng):
    """
    Return (Downtown, miles) for the closest active downtown, or None.

    Loads the whole table once per call. That is deliberate: the table holds
    tens of rows, and a bounding-box query would need spatial indexes the
    project does not have. If it ever grows past a few hundred rows, revisit.
    """
    from listings.models import Downtown  # local: avoids a circular import

    if lat is None or lng is None:
        return None

    best = None
    for downtown in Downtown.objects.filter(is_active=True):
        miles = haversine_miles(lat, lng, downtown.latitude, downtown.longitude)
        if miles is None:
            continue
        if best is None or miles < best[1]:
            best = (downtown, miles)

    return best


def assign_instance(instance) -> bool:
    """
    Set nearest_downtown / downtown_distance_miles on a Listing (does NOT save).

    Returns True when a downtown was matched. On no match the fields are
    cleared, so a listing that moves out of every metro's range stops claiming
    a stale downtown.
    """
    match = nearest_downtown(instance.latitude, instance.longitude)

    if match is None:
        instance.nearest_downtown = None
        instance.downtown_distance_miles = None
        return False

    downtown, miles = match
    instance.nearest_downtown = downtown
    instance.downtown_distance_miles = round(miles, 1)
    return True
