"""
Google Geocoding — convert a street address into real (lat, lng) coordinates.

Usage:
    from listings.services.geocoding import geocode_address, geocode_instance

    coords = geocode_address("4521 Maple Ave, Irving, TX 75038, USA")
    # → (32.81..., -96.94...) or None

    geocode_instance(listing)   # geocodes + stamps the model in-place (no save)

Coordinates never change for a fixed address, so callers should persist the
result and only re-geocode when the address actually changes (tracked via the
model's `geocoded_address` field).
"""
from __future__ import annotations

import logging

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

_GEOCODE_URL = 'https://maps.googleapis.com/maps/api/geocode/json'
_TIMEOUT = 6  # seconds


def geocode_address(address: str) -> tuple[float, float] | None:
    """Return (lat, lng) for an address, or None if it can't be resolved."""
    address = (address or '').strip()
    if not address:
        return None

    # Prefer the dedicated server-side key (IP/API-restricted); fall back to the
    # browser key. A referrer-restricted browser key will be denied server-side.
    api_key = getattr(settings, 'GOOGLE_GEOCODING_API_KEY', '') or getattr(settings, 'GOOGLE_MAPS_API_KEY', '')
    if not api_key:
        logger.warning('geocode_address: no Google geocoding key set — skipping')
        return None

    try:
        resp = requests.get(
            _GEOCODE_URL,
            params={'address': address, 'key': api_key},
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
    except (requests.RequestException, ValueError) as exc:
        logger.warning('geocode_address: request failed for %r: %s', address, exc)
        return None

    status = data.get('status')
    if status != 'OK' or not data.get('results'):
        # ZERO_RESULTS, OVER_QUERY_LIMIT, REQUEST_DENIED, etc.
        logger.info('geocode_address: %s for %r', status, address)
        return None

    loc = data['results'][0]['geometry']['location']
    return float(loc['lat']), float(loc['lng'])


def geocode_instance(instance, *, force: bool = False) -> bool:
    """
    Geocode a Listing/Community in-place (does NOT save).

    Skips the API call when the address is unchanged and coords already exist,
    unless `force=True`. Returns True if lat/lng were set on this call.
    """
    address = getattr(instance, 'full_address', '') or ''
    if not address:
        return False

    already_geocoded = (
        instance.latitude is not None
        and instance.longitude is not None
        and instance.geocoded_address == address
    )
    if already_geocoded and not force:
        return False

    coords = geocode_address(address)
    if coords is None:
        return False

    instance.latitude, instance.longitude = coords
    instance.geocoded_address = address
    return True
