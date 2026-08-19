"""
GreatSchools — nearby schools and their ratings for a location.

Usage:
    from listings.services.greatschools import fetch_nearby_schools, sync_instance

    rows = fetch_nearby_schools(32.914178, -96.964342)
    # → [{'gs_id': '...', 'name': 'Freedom Elementary School', ...}] or None

    sync_instance(listing)   # fetches + writes School / ListingSchool rows

Ratings move about once a year (GreatSchools republishes on the state testing
cycle), so callers persist the result and only refresh when it goes stale —
tracked via Listing.schools_updated and the STALE_AFTER window below.

Unlike listings.services.walkscore, sync_instance WRITES to the database. It has
to: the result is a set of related rows, not a handful of scalar fields that a
caller could stamp onto an instance and save itself.

Attribution: GreatSchools' terms require ratings to be shown as theirs, with a
link to the school's profile. `School.profile_url` is stored for that purpose —
render it wherever a rating is shown.

Response field names: the API has shipped several spellings of the same field
across versions and tiers ('universal-id' vs 'universalId', 'gradeRange' vs
'grade-range'). `_pick` accepts any of them rather than pinning one, so a tier
change doesn't silently blank the cards. If a field arrives under a name not
listed here it will read as absent — check a raw response before assuming the
school simply has no data.
"""
from __future__ import annotations

import logging
from datetime import timedelta

import requests
from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)

_NEARBY_URL = 'https://gs-api.greatschools.org/v2/nearby-schools'
_TIMEOUT = 8  # seconds

# How long a listing's stored schools stay fresh before a refresh run refetches.
STALE_AFTER = timedelta(days=180)

# How many schools to store per listing. The card shows one per level; asking
# for a few more leaves room for levels that have no school within the radius.
DEFAULT_LIMIT = 12

# Search radius in miles. Wide enough that rural listings still get a high
# school, narrow enough that suburban ones don't fill up with another district's.
DEFAULT_RADIUS = 10

# Listings on the same block share the same schools, so responses are cached on
# a coarse coordinate grid. 3 decimal places ≈ 110m — well below the distance at
# which the nearby-school set changes, and enough to collapse a whole apartment
# community's units into one API call.
_CACHE_PRECISION = 3
_CACHE_TTL = 60 * 60 * 24  # 1 day — only spans a single import run


def _pick(row: dict, *keys, default=None):
    """First present, non-empty value among `keys`. See the module docstring."""
    for key in keys:
        value = row.get(key)
        if value not in (None, ''):
            return value
    return default


def _to_int(value):
    """Ratings arrive as ints, numeric strings, or 'NR' for not-rated."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _to_decimal(value):
    try:
        return round(float(value), 1)
    except (TypeError, ValueError):
        return None


def _normalize(row: dict) -> dict | None:
    """
    Map one API school onto our field names, or None if it has no usable id.

    A row without an id can't be stored — we'd create a duplicate School on
    every refresh — so it's dropped rather than guessed at from the name.
    """
    gs_id = _pick(row, 'universal-id', 'universalId', 'universal_id', 'id')
    if not gs_id:
        return None

    level_codes = _pick(row, 'level-codes', 'levelCodes', 'level_codes', default='')

    return {
        'gs_id': str(gs_id)[:40],
        'name': str(_pick(row, 'name', 'school-name', default=''))[:200],
        'school_type': str(_pick(row, 'type', 'school-type', 'schoolType', default=''))[:20],
        'grade_range': str(_pick(row, 'gradeRange', 'grade-range', 'grade_range',
                                 'level', default=''))[:40],
        'level_codes': str(level_codes)[:20],
        'city': str(_pick(row, 'city', default=''))[:100],
        'state': str(_pick(row, 'state', default=''))[:50],
        'rating': _to_int(_pick(row, 'rating', 'gsRating', 'gs-rating')),
        'test_score_rating': _to_int(_pick(
            row, 'test-score-rating', 'testScoreRating', 'test_score_rating')),
        'college_readiness_rating': _to_int(_pick(
            row, 'college-readiness-rating', 'collegeReadinessRating',
            'college_readiness_rating')),
        'student_progress_rating': _to_int(_pick(
            row, 'student-progress-rating', 'studentProgressRating',
            'student_progress_rating')),
        'profile_url': str(_pick(row, 'overview-url', 'overviewUrl', 'profile-url',
                                 'web-site', default=''))[:500],
        # Not a School field — carried through for the ListingSchool join.
        'distance_miles': _to_decimal(_pick(row, 'distance')),
    }


def fetch_nearby_schools(lat, lng, *, limit: int = DEFAULT_LIMIT,
                         radius: int = DEFAULT_RADIUS) -> list[dict] | None:
    """
    Return normalized nearby-school dicts for a coordinate, or None on failure.

    None means "the lookup failed" and an empty list means "this location
    genuinely has no schools in range" — callers must not treat them alike, or a
    quota error would wipe stored schools off every listing it touched.
    """
    api_key = getattr(settings, 'GREATSCHOOLS_API_KEY', '')
    if not api_key:
        logger.warning('fetch_nearby_schools: no GreatSchools key set — skipping')
        return None

    if lat is None or lng is None:
        return None

    lat_f, lng_f = float(lat), float(lng)
    cache_key = (f'greatschools:{round(lat_f, _CACHE_PRECISION)}:'
                 f'{round(lng_f, _CACHE_PRECISION)}:{limit}:{radius}')
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    try:
        resp = requests.get(
            _NEARBY_URL,
            params={
                'lat': lat_f,
                'lon': lng_f,
                'limit': limit,
                'distance': radius,
                'level_codes': 'e,m,h',
            },
            headers={'x-api-key': api_key, 'Accept': 'application/json'},
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
    except (requests.RequestException, ValueError) as exc:
        logger.warning('fetch_nearby_schools: request failed for (%s,%s): %s',
                       lat, lng, exc)
        return None

    raw = data.get('schools') if isinstance(data, dict) else data
    if not isinstance(raw, list):
        logger.warning('fetch_nearby_schools: unexpected payload shape for (%s,%s)',
                       lat, lng)
        return None

    schools = [s for s in (_normalize(row) for row in raw) if s]
    cache.set(cache_key, schools, _CACHE_TTL)
    return schools


def is_stale(instance) -> bool:
    """True when the instance has never been synced, or its schools aged out."""
    if instance.schools_updated is None:
        return True
    return timezone.now() - instance.schools_updated > STALE_AFTER


def sync_instance(instance, *, force: bool = False) -> int | None:
    """
    Fetch nearby schools for a Listing and persist them.

    Returns the number of schools linked, or None when nothing was attempted or
    the fetch failed. Unlike walkscore.score_instance this saves — it writes
    School rows, ListingSchool links, and the listing's schools_updated stamp.

    Links the listing no longer matches are removed, so a school that moved out
    of range disappears instead of lingering. That deletion only runs on a
    successful fetch, which is why a failed fetch returns early above.
    """
    from listings.models import ListingSchool, School  # local: avoids a cycle

    if instance.latitude is None or instance.longitude is None:
        return None
    if not force and not is_stale(instance):
        return None

    rows = fetch_nearby_schools(instance.latitude, instance.longitude)
    if rows is None:
        return None

    with transaction.atomic():
        keep_ids = []
        for row in rows:
            distance = row.pop('distance_miles', None)
            gs_id = row.pop('gs_id')
            row['level_rank'] = School.rank_for_levels(row.get('level_codes', ''))

            school, _ = School.objects.update_or_create(gs_id=gs_id, defaults=row)
            ListingSchool.objects.update_or_create(
                listing=instance, school=school,
                defaults={'distance_miles': distance},
            )
            keep_ids.append(school.pk)

        instance.nearby_schools.exclude(school_id__in=keep_ids).delete()

        instance.schools_updated = timezone.now()
        instance.save(update_fields=['schools_updated'])

    return len(keep_ids)
