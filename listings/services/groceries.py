"""
Google Places — nearby grocery chains for a location.

Usage:
    from listings.services.groceries import fetch_nearby_groceries, sync_instance

    fetch_nearby_groceries(32.914178, -96.964342)
    # → [{'place_id': ..., 'chain': 'Walmart', ...}] or None

    sync_instance(listing)   # fetches + writes GroceryStore / link rows

Why a chain whitelist rather than a Places type filter
------------------------------------------------------
Asking Places for grocery types alone returns things nobody would call a
grocery run: petrol-station convenience stores are routinely typed as grocery,
and the branded fuel and pharmacy outlets that big chains operate come back as
separate places sitting on the same car park. So the type filter is only a
first pass — a place is kept only if its name resolves to a known chain in
GROCERY_CHAINS *and* does not look like a fuel, pharmacy or auto outlet.

That means the list is deliberately incomplete: a good independent grocer is
excluded because we cannot tell it apart from a corner shop by name. Adding a
chain is a one-line change below.

Response field names follow Places API (New), which is what a newly enabled
key gets. The `includedTypes` values and how warehouse clubs are typed are the
parts worth verifying against a real response first — see the module notes in
services/greatschools.py for the same caveat.
"""
from __future__ import annotations

import logging
import re
from datetime import timedelta

import requests
from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.utils import timezone

from listings.services.distance import haversine_miles

logger = logging.getLogger(__name__)

_NEARBY_URL = 'https://places.googleapis.com/v1/places:searchNearby'
_TIMEOUT = 8  # seconds

# Store locations move rarely; a store opening or closing is the real reason to
# refresh, and that is on the order of years for these chains.
STALE_AFTER = timedelta(days=180)

# Metres. ~5 miles — beyond this a grocery run stops being a neighbourhood fact.
DEFAULT_RADIUS_M = 8_000

# Places caps this at 20. The whitelist discards most of a response, so ask for
# the maximum and filter down rather than paging.
MAX_RESULTS = 20

# How many chains the card shows, nearest first.
DEFAULT_CHAIN_LIMIT = 5

# Broad on purpose: the whitelist below does the real narrowing, and warehouse
# clubs are not consistently typed as supermarkets.
INCLUDED_TYPES = ['supermarket', 'grocery_store', 'warehouse_store']

# Canonical chain name → name fragments to match, already normalised the way
# _normalize_name normalises (lowercase, apostrophes dropped, punctuation to
# spaces). Order matters only in that the first match wins.
GROCERY_CHAINS = (
    ('Walmart',        ('walmart',)),
    ("Sam's Club",     ('sams club',)),
    ('Costco',         ('costco',)),
    ('Kroger',         ('kroger',)),
    ('H-E-B',          ('h e b', 'heb')),
    ('Central Market', ('central market',)),
    ('Tom Thumb',      ('tom thumb',)),
    ('Albertsons',     ('albertsons',)),
    ('Randalls',       ('randalls',)),
    ('Market Street',  ('market street',)),
    ('Brookshire’s',   ('brookshires', 'brookshire s')),
    ('Target',         ('target',)),
    ('Aldi',           ('aldi',)),
    ('Lidl',           ('lidl',)),
    ('Trader Joe’s',   ('trader joes',)),
    ('Whole Foods',    ('whole foods',)),
    ('Sprouts',        ('sprouts',)),
    ('Natural Grocers',('natural grocers',)),
    ('Fiesta Mart',    ('fiesta mart',)),
    ('El Rancho',      ('el rancho',)),
    ('WinCo Foods',    ('winco',)),
    ('Publix',         ('publix',)),
    ('Safeway',        ('safeway',)),
)

# Branded outlets that share a chain name but are not somewhere you buy food.
# Word-boundary matched so 'Gasper Foods' or a street called Fuel Lane cannot
# knock out a real store.
_NON_GROCERY = re.compile(
    r'\b(gas|gasoline|fuel|fueling|petrol|pharmacy|drive\s*thru|'
    r'auto|automotive|tire|tyre|vision|optical|photo|garden\s*center)\b'
)

# Places types that disqualify a place outright, whatever it is called.
_EXCLUDED_TYPES = {'gas_station', 'car_repair', 'car_wash', 'pharmacy'}

# Same coordinate-grid cache as the schools service: units in one community
# share a response instead of each paying for a call. 3 dp ≈ 110m.
_CACHE_PRECISION = 3
_CACHE_TTL = 60 * 60 * 24  # 1 day — spans a single import run


def _normalize_name(name: str) -> str:
    """
    Fold a store name to the form GROCERY_CHAINS aliases are written in.

    Apostrophes are deleted rather than spaced so "Sam's Club" reads as
    "sams club"; every other punctuation mark becomes a space so "H-E-B plus!"
    reads as "h e b plus" and still matches the 'h e b' alias.
    """
    lowered = (name or '').lower().replace('’', '').replace("'", '')
    return re.sub(r'\s+', ' ', re.sub(r'[^a-z0-9]+', ' ', lowered)).strip()


def match_chain(name: str) -> str | None:
    """
    Canonical chain name for a store name, or None if it is not a known chain.

    Returns None for fuel, pharmacy and auto outlets even when the chain part
    matches — "Costco Gasoline" is a petrol station, not a grocery run, and
    excluding those is the whole point of the whitelist.
    """
    normalized = _normalize_name(name)
    if not normalized or _NON_GROCERY.search(normalized):
        return None

    for canonical, aliases in GROCERY_CHAINS:
        if any(alias in normalized for alias in aliases):
            return canonical
    return None


def _normalize(place: dict) -> dict | None:
    """Map one Places result onto our field names, or None to discard it."""
    place_id = place.get('id')
    if not place_id:
        return None

    if set(place.get('types') or []) & _EXCLUDED_TYPES:
        return None

    name = ((place.get('displayName') or {}).get('text') or '').strip()
    chain = match_chain(name)
    if chain is None:
        return None

    location = place.get('location') or {}
    return {
        'place_id': str(place_id)[:200],
        'chain': chain,
        'name': name[:200],
        'address': str(place.get('formattedAddress') or '')[:300],
        'latitude': location.get('latitude'),
        'longitude': location.get('longitude'),
    }


def fetch_nearby_groceries(lat, lng, *, radius_m: int = DEFAULT_RADIUS_M) -> list[dict] | None:
    """
    Return normalized grocery dicts near a coordinate, or None on failure.

    None means the lookup failed; an empty list means there are genuinely no
    recognised chains in range. Callers must not treat them alike, or a quota
    error would wipe stored stores off every listing it touched.
    """
    api_key = (getattr(settings, 'GOOGLE_PLACES_API_KEY', '')
               or getattr(settings, 'GOOGLE_GEOCODING_API_KEY', '')
               or getattr(settings, 'GOOGLE_MAPS_API_KEY', ''))
    if not api_key:
        logger.warning('fetch_nearby_groceries: no Google Places key set — skipping')
        return None

    if lat is None or lng is None:
        return None

    lat_f, lng_f = float(lat), float(lng)
    cache_key = (f'groceries:{round(lat_f, _CACHE_PRECISION)}:'
                 f'{round(lng_f, _CACHE_PRECISION)}:{radius_m}')
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    try:
        resp = requests.post(
            _NEARBY_URL,
            json={
                'includedTypes': INCLUDED_TYPES,
                'maxResultCount': MAX_RESULTS,
                'locationRestriction': {
                    'circle': {
                        'center': {'latitude': lat_f, 'longitude': lng_f},
                        'radius': float(radius_m),
                    }
                },
            },
            headers={
                'Content-Type': 'application/json',
                'X-Goog-Api-Key': api_key,
                # Places (New) bills by the fields requested — ask only for what
                # is stored, or the call moves to a dearer SKU for nothing.
                'X-Goog-FieldMask': ('places.id,places.displayName,'
                                     'places.formattedAddress,places.location,'
                                     'places.types'),
            },
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
    except (requests.RequestException, ValueError) as exc:
        logger.warning('fetch_nearby_groceries: request failed for (%s,%s): %s',
                       lat, lng, exc)
        return None

    raw = data.get('places') if isinstance(data, dict) else None
    if raw is None:
        # Places returns {} rather than an empty list when nothing matches.
        raw = []
    if not isinstance(raw, list):
        logger.warning('fetch_nearby_groceries: unexpected payload for (%s,%s)', lat, lng)
        return None

    stores = [s for s in (_normalize(p) for p in raw) if s]
    cache.set(cache_key, stores, _CACHE_TTL)
    return stores


def is_stale(instance) -> bool:
    """True when the instance has never been synced, or its stores aged out."""
    if instance.groceries_updated is None:
        return True
    return timezone.now() - instance.groceries_updated > STALE_AFTER


def _nearest_per_chain(stores, lat, lng, limit):
    """
    Keep the closest branch of each chain, nearest first, capped at `limit`.

    Without this the card reads "Walmart, Walmart, Walmart" in any suburb — a
    renter wants to know which chains are near, not how many branches.
    """
    best = {}
    for store in stores:
        miles = haversine_miles(lat, lng, store.get('latitude'), store.get('longitude'))
        if miles is None:
            continue
        current = best.get(store['chain'])
        if current is None or miles < current[1]:
            best[store['chain']] = (store, miles)

    ranked = sorted(best.values(), key=lambda pair: pair[1])
    return ranked[:limit]


def sync_instance(instance, *, force: bool = False,
                  limit: int = DEFAULT_CHAIN_LIMIT) -> int | None:
    """
    Fetch nearby grocery chains for a Listing and persist them.

    Returns the number of stores linked, or None when nothing was attempted or
    the fetch failed. Like the schools sync this saves, because the result is a
    set of related rows rather than a few scalar fields.
    """
    from listings.models import (CommunityGroceryStore, GroceryStore,  # local: cycle
                                 ListingGroceryStore)

    link_model, owner_field = ((CommunityGroceryStore, 'community')
                               if instance._meta.model_name == 'community'
                               else (ListingGroceryStore, 'listing'))

    if instance.latitude is None or instance.longitude is None:
        return None
    if not force and not is_stale(instance):
        return None

    rows = fetch_nearby_groceries(instance.latitude, instance.longitude)
    if rows is None:
        return None

    ranked = _nearest_per_chain(rows, instance.latitude, instance.longitude, limit)

    with transaction.atomic():
        keep_ids = []
        for row in ranked:
            store_data = dict(row[0])
            miles = row[1]
            place_id = store_data.pop('place_id')

            store, _ = GroceryStore.objects.update_or_create(
                place_id=place_id, defaults=store_data)
            link_model.objects.update_or_create(
                **{owner_field: instance}, store=store,
                defaults={'distance_miles': round(miles, 1)},
            )
            keep_ids.append(store.pk)

        # Only runs on a successful fetch — see the None check above.
        instance.nearby_groceries.exclude(store_id__in=keep_ids).delete()

        instance.groceries_updated = timezone.now()
        instance.save(update_fields=['groceries_updated'])

    return len(keep_ids)
