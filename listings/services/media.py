"""
Fetch remote listing photos into our own storage (R2 in prod, local in dev).

Ported from the retired `sync_realty_mole` command, which is the only part of it
worth keeping.

Rights note (blueprint §14): calling this means asserting we may host and
display the images. A public image URL is not permission. Partner agreements
must grant it before their photos are pulled through here.
"""
from __future__ import annotations

import logging
import time

import requests
from django.core.files.base import ContentFile

from listings.models import ListingImage

logger = logging.getLogger(__name__)

MAX_PHOTOS = 6              # balances listing coverage against storage cost
_TIMEOUT = 12
_ALLOWED_EXT = ('jpg', 'jpeg', 'png', 'webp')
_CONTENT_TYPE_EXT = {
    'image/jpeg': 'jpg',
    'image/jpg':  'jpg',
    'image/png':  'png',
    'image/webp': 'webp',
}


def save_remote_photos(owner_obj, photo_urls, *, max_photos: int = MAX_PHOTOS,
                       prefix: str = 'partner', image_model=None,
                       related_field: str = 'listing') -> int:
    """
    Download up to `max_photos` images and attach them to `owner_obj`.

    Defaults attach `ListingImage` to a Listing; pass `image_model` /
    `related_field` to attach `CommunityImage` to a Community instead.

    A failed image never fails the import — a listing with four of six photos is
    worth far more than no listing at all.
    """
    image_model = image_model or ListingImage
    saved = 0

    for index, url in enumerate(photo_urls[:max_photos]):
        try:
            response = requests.get(url, timeout=_TIMEOUT, stream=True)
            response.raise_for_status()

            ext = _extension_for(response.headers.get('Content-Type', ''), url)
            if ext not in _ALLOWED_EXT:
                logger.info('Skipping non-image photo for %s: %s', owner_obj.pk, url)
                continue

            image = image_model(**{related_field: owner_obj}, order=index)
            # Bare filename only — the field's own `upload_to` supplies the
            # directory. Passing one here nested it twice.
            image.image.save(f'{prefix}_{owner_obj.pk}_{index}.{ext}',
                             ContentFile(response.content), save=True)
            saved += 1
            time.sleep(0.1)      # be gentle with the partner's image host

        except Exception:        # noqa: BLE001 — one bad photo must not fail the row
            logger.warning('Photo download failed for %s url %s',
                           owner_obj.pk, url, exc_info=True)

    return saved


def _extension_for(content_type: str, url: str) -> str:
    for candidate, ext in _CONTENT_TYPE_EXT.items():
        if candidate in content_type:
            return ext
    path = url.split('?')[0]
    return path.rsplit('.', 1)[-1].lower() if '.' in path else 'jpg'
