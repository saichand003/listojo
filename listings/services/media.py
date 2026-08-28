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


def sync_remote_photos(owner_obj, photo_urls, *, max_photos: int = MAX_PHOTOS,
                       prefix: str = 'partner', image_model=None,
                       related_field: str = 'listing') -> tuple[int, int]:
    """
    Reconcile a feed's photos against what is already stored.

    Downloads URLs that are new, removes images whose URL has left the file,
    and leaves anything hand-uploaded (blank `source_url`) alone. A partner
    adding one photo to next week's CSV should cost one download, not six —
    and should never wipe what a person added in admin.

    The alternative, refusing to touch a property that already has any photo,
    made partner media write-once: a swapped hero shot could not be corrected
    without staff deleting rows by hand.

    Returns (saved, removed).
    """
    image_model = image_model or ListingImage

    wanted: list[str] = []
    for url in photo_urls:
        if url not in wanted:
            wanted.append(url)
    wanted = wanted[:max_photos]

    from_feed = {image.source_url: image
                 for image in owner_obj.images.exclude(source_url='')}

    removed = 0
    for url, image in from_feed.items():
        if url not in wanted:
            # Drop the stored object too, or R2 accumulates files nothing
            # references. Not transactional — a rollback leaves them deleted.
            image.image.delete(save=False)
            image.delete()
            removed += 1

    saved = 0
    for index, url in enumerate(wanted):
        existing = from_feed.get(url)
        if existing is not None:
            if existing.order != index:
                existing.order = index
                existing.save(update_fields=['order'])
            continue
        if _download_photo(image_model, owner_obj, url, index,
                           prefix=prefix, related_field=related_field):
            saved += 1

    return saved, removed


def _download_photo(image_model, owner_obj, url: str, index: int, *,
                    prefix: str, related_field: str) -> bool:
    """
    Fetch one image into our own storage. A failure is never fatal.

    One bad photo must not fail the row — a listing with four of six photos is
    worth far more than no listing at all.
    """
    try:
        response = requests.get(url, timeout=_TIMEOUT, stream=True)
        response.raise_for_status()

        ext = _extension_for(response.headers.get('Content-Type', ''), url)
        if ext not in _ALLOWED_EXT:
            logger.info('Skipping non-image photo for %s: %s', owner_obj.pk, url)
            return False

        image = image_model(**{related_field: owner_obj}, order=index,
                            source_url=url)
        # Bare filename only — the field's own `upload_to` supplies the
        # directory. Passing one here nested it twice.
        image.image.save(f'{prefix}_{owner_obj.pk}_{index}.{ext}',
                         ContentFile(response.content), save=True)
        time.sleep(0.1)      # be gentle with the partner's image host
        return True

    except Exception:        # noqa: BLE001 — one bad photo must not fail the row
        logger.warning('Photo download failed for %s url %s',
                       owner_obj.pk, url, exc_info=True)
        return False


def _extension_for(content_type: str, url: str) -> str:
    for candidate, ext in _CONTENT_TYPE_EXT.items():
        if candidate in content_type:
            return ext
    path = url.split('?')[0]
    return path.rsplit('.', 1)[-1].lower() if '.' in path else 'jpg'
