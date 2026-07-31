"""
Walk Score — neighborhood walkability, transit and bike scores for a location.

Usage:
    from listings.services.walkscore import fetch_scores, score_instance

    data = fetch_scores(32.914178, -96.964342, '1424 Chase Lane, Irving, TX')
    # → {'walk_score': 42, 'walk_score_description': 'Car-Dependent', ...} or None

    score_instance(listing)   # fetches + stamps the model in-place (no save)

Scores change slowly (Walk Score recomputes on the order of months), so callers
should persist the result and only refresh when it goes stale — tracked via the
model's `walk_score_updated` timestamp and the STALE_AFTER window below.

Attribution: Walk Score's API terms require that the score is displayed with a
link back to their site. `walk_score_link` is stored for exactly that purpose —
render it wherever a score is shown.
"""
from __future__ import annotations

import logging
from datetime import timedelta

import requests
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

_SCORE_URL = 'https://api.walkscore.com/score'
_TIMEOUT = 6  # seconds

# How long a stored score stays fresh before a refresh run will re-fetch it.
STALE_AFTER = timedelta(days=90)

# Walk Score API status codes worth distinguishing in the logs.
_STATUS_OK = 1
_STATUS_PENDING = 2  # score is being calculated — retry later, not an error


def fetch_scores(lat, lng, address: str = '') -> dict | None:
    """
    Return Walk/Transit/Bike scores for a coordinate, or None on failure.

    Keys mirror the model field names so callers can splat the result onto an
    instance. Transit and bike scores are absent (None) in areas Walk Score has
    no data for — a listing can legitimately have a walk score and nothing else.
    """
    api_key = getattr(settings, 'WALKSCORE_API_KEY', '')
    if not api_key:
        logger.warning('fetch_scores: no Walk Score key set — skipping')
        return None

    if lat is None or lng is None:
        return None

    try:
        resp = requests.get(
            _SCORE_URL,
            params={
                'format': 'json',
                'lat': float(lat),
                'lon': float(lng),
                'address': address or '',
                'transit': 1,
                'bike': 1,
                'wsapikey': api_key,
            },
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
    except (requests.RequestException, ValueError) as exc:
        logger.warning('fetch_scores: request failed for (%s,%s): %s', lat, lng, exc)
        return None

    status = data.get('status')
    if status != _STATUS_OK:
        # 2 = still calculating, 30/31 = bad coords or key, 40+ = quota.
        level = logger.info if status == _STATUS_PENDING else logger.warning
        level('fetch_scores: status %s for (%s,%s)', status, lat, lng)
        return None

    transit = data.get('transit') or {}
    bike = data.get('bike') or {}

    return {
        'walk_score': data.get('walkscore'),
        'walk_score_description': data.get('description') or '',
        'transit_score': transit.get('score'),
        'transit_description': transit.get('description') or '',
        'bike_score': bike.get('score'),
        'bike_description': bike.get('description') or '',
        'walk_score_link': data.get('ws_link') or '',
    }


def is_stale(instance) -> bool:
    """True when the instance has no score, or its score has aged out."""
    if instance.walk_score is None or instance.walk_score_updated is None:
        return True
    return timezone.now() - instance.walk_score_updated > STALE_AFTER


def score_instance(instance, *, force: bool = False) -> bool:
    """
    Fetch Walk Score data for a Listing in-place (does NOT save).

    Skips the API call when a fresh score is already stored, unless force=True.
    Returns True if scores were set on this call.
    """
    if instance.latitude is None or instance.longitude is None:
        return False
    if not force and not is_stale(instance):
        return False

    data = fetch_scores(instance.latitude, instance.longitude, instance.full_address)
    if data is None:
        return False

    for field, value in data.items():
        setattr(instance, field, value)
    instance.walk_score_updated = timezone.now()
    return True
