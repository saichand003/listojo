"""
Sync rental and sale listings from Realty Mole (RapidAPI) into the database.
Photos are downloaded and stored in R2 (or local media in dev).

Usage:
    python manage.py sync_realty_mole
    python manage.py sync_realty_mole --cities Dallas Plano
    python manage.py sync_realty_mole --category rentals
    python manage.py sync_realty_mole --limit 50 --dry-run
    python manage.py sync_realty_mole --no-images
"""
import logging
import time

import requests
from django.conf import settings
from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError

from listings.models import Listing, ListingImage

logger = logging.getLogger(__name__)

_API_HOST = 'realty-mole-property-api.p.rapidapi.com'
_API_BASE  = f'https://{_API_HOST}'
_MAX_PHOTOS = 6   # per listing — balances coverage vs. R2 storage

_PROP_TYPE_MAP = {
    'Single Family':  'single_family',
    'Condo':          'condo',
    'Apartment':      'apartment',
    'Townhouse':      'townhouse',
    'Multi Family':   'apartment',
    'Manufactured':   'house',
    'Land':           'land',
    'Ranch':          'ranch',
    'Loft':           'loft',
    'Studio':         'studio',
}

_DFW_CITIES = [
    'Dallas', 'Fort Worth', 'Arlington', 'Plano', 'Irving',
    'Garland', 'Frisco', 'McKinney', 'Grand Prairie', 'Denton',
    'Richardson', 'Lewisville', 'Allen', 'Carrollton', 'Mesquite',
]


class Command(BaseCommand):
    help = 'Import listings from Realty Mole API (RapidAPI) including photos'

    def add_arguments(self, parser):
        parser.add_argument('--cities', nargs='+', default=_DFW_CITIES,
                            help='Cities to sync (default: DFW metros)')
        parser.add_argument('--category', choices=['rentals', 'properties', 'all'],
                            default='all', help='Which category to sync')
        parser.add_argument('--limit', type=int, default=50,
                            help='Max listings per city per category (max 500)')
        parser.add_argument('--dry-run', action='store_true',
                            help='Print what would be imported without saving')
        parser.add_argument('--no-images', action='store_true',
                            help='Skip photo download (faster, less storage)')

    def handle(self, *args, **options):
        api_key = settings.REALTY_MOLE_API_KEY
        if not api_key:
            raise CommandError(
                'REALTY_MOLE_API_KEY is not set. '
                'Add it to your Railway environment variables.'
            )

        owner = User.objects.filter(is_superuser=True).first()
        if not owner:
            raise CommandError('No superuser found. Run: python manage.py createsuperuser')

        cities     = options['cities']
        category   = options['category']
        limit      = min(options['limit'], 500)
        dry_run    = options['dry_run']
        no_images  = options['no_images']

        headers = {
            'X-RapidAPI-Key':  api_key,
            'X-RapidAPI-Host': _API_HOST,
        }

        total_created = total_updated = total_skipped = total_photos = 0

        for city in cities:
            if category in ('rentals', 'all'):
                c, u, s, p = self._sync(headers, city, 'rentals', limit, owner, dry_run, no_images)
                total_created += c; total_updated += u
                total_skipped += s; total_photos  += p
                time.sleep(0.4)

            if category in ('properties', 'all'):
                c, u, s, p = self._sync(headers, city, 'properties', limit, owner, dry_run, no_images)
                total_created += c; total_updated += u
                total_skipped += s; total_photos  += p
                time.sleep(0.4)

        label = '[DRY RUN] ' if dry_run else ''
        self.stdout.write(self.style.SUCCESS(
            f'{label}Done — {total_created} created, {total_updated} updated, '
            f'{total_skipped} skipped, {total_photos} photos saved'
        ))

    # ─────────────────────────────────────────────────────────────────────────

    def _sync(self, headers, city, category, limit, owner, dry_run, no_images):
        endpoint = '/rentalListings' if category == 'rentals' else '/saleListings'
        try:
            resp = requests.get(
                _API_BASE + endpoint,
                headers=headers,
                params={'city': city, 'state': 'TX', 'limit': limit},
                timeout=20,
            )
            resp.raise_for_status()
        except requests.RequestException as exc:
            self.stderr.write(f'  [{city}/{category}] API error: {exc}')
            return 0, 0, 0, 0

        items = resp.json()
        if not isinstance(items, list):
            self.stderr.write(f'  [{city}/{category}] Unexpected response shape')
            return 0, 0, 0, 0

        created = updated = skipped = photos = 0
        for item in items:
            result, photo_count = self._upsert(item, category, owner, dry_run, no_images)
            if result == 'created':
                created += 1
            elif result == 'updated':
                updated += 1
            else:
                skipped += 1
            photos += photo_count

        self.stdout.write(
            f'  {city}/{category}: {created} new, {updated} updated, '
            f'{skipped} skipped, {photos} photos'
        )
        return created, updated, skipped, photos

    def _upsert(self, item, category, owner, dry_run, no_images):
        address = (item.get('formattedAddress') or item.get('addressLine1', '')).strip()
        if not address:
            return 'skipped', 0

        price = item.get('price') or item.get('listPrice')
        if not price:
            return 'skipped', 0

        city_raw  = item.get('city', '').strip()
        bedrooms  = item.get('bedrooms')
        prop_type = item.get('propertyType', '')
        photos    = item.get('photos') or item.get('images') or []

        title = self._make_title(bedrooms, prop_type, city_raw)

        defaults = {
            'owner':          owner,
            'title':          title,
            'description':    self._make_description(item),
            'price':          price,
            'price_unit':     'mo' if category == 'rentals' else '',
            'category':       category,
            'address_line':   address,
            'city':           city_raw.lower(),
            'state':          item.get('state', 'TX'),
            'zip_code':       str(item.get('zipCode', '')),
            'bedrooms':       bedrooms,
            'square_footage': item.get('squareFootage'),
            'year_built':     item.get('yearBuilt'),
            'property_type':  _PROP_TYPE_MAP.get(prop_type, ''),
            'status':         'active',
            'source_type':    'realty_mole',
        }

        if dry_run:
            exists = Listing.objects.filter(
                address_line=address, source_type='realty_mole'
            ).exists()
            photo_count = len(photos[:_MAX_PHOTOS]) if not no_images else 0
            self.stdout.write(
                f'    {"UPDATE" if exists else "CREATE"}: {title} — '
                f'${price} ({photo_count} photos)'
            )
            return ('created' if not exists else 'updated'), 0

        listing, was_created = Listing.objects.update_or_create(
            address_line=address,
            source_type='realty_mole',
            defaults=defaults,
        )

        # Only download photos for new listings, or listings with no images yet
        photo_count = 0
        if not no_images and not listing.images.exists() and photos:
            photo_count = self._save_photos(listing, photos)

        return ('created' if was_created else 'updated'), photo_count

    def _save_photos(self, listing, photo_urls):
        saved = 0
        for i, url in enumerate(photo_urls[:_MAX_PHOTOS]):
            try:
                resp = requests.get(url, timeout=12, stream=True)
                resp.raise_for_status()

                content_type = resp.headers.get('Content-Type', 'image/jpeg')
                ext = self._ext_from_content_type(content_type, url)
                if ext not in ('jpg', 'jpeg', 'png', 'webp'):
                    continue

                filename = f'listing_images/rm_{listing.pk}_{i}.{ext}'
                img_obj  = ListingImage(listing=listing, order=i)
                img_obj.image.save(filename, ContentFile(resp.content), save=True)
                saved += 1
                time.sleep(0.1)   # be gentle with remote servers

            except Exception as exc:
                logger.warning('Photo download failed for listing %s url %s: %s',
                               listing.pk, url, exc)
        return saved

    @staticmethod
    def _ext_from_content_type(content_type, url):
        ct_map = {
            'image/jpeg': 'jpg',
            'image/jpg':  'jpg',
            'image/png':  'png',
            'image/webp': 'webp',
        }
        for ct, ext in ct_map.items():
            if ct in content_type:
                return ext
        # Fall back to URL extension
        path = url.split('?')[0]
        return path.rsplit('.', 1)[-1].lower() if '.' in path else 'jpg'

    @staticmethod
    def _make_title(bedrooms, prop_type, city):
        beds   = f'{bedrooms}BR ' if bedrooms else ''
        ptype  = prop_type or 'Home'
        city_p = f' in {city}' if city else ''
        return f'{beds}{ptype}{city_p}'

    @staticmethod
    def _make_description(item):
        parts = []
        if item.get('squareFootage'):
            parts.append(f"{item['squareFootage']:,} sq ft")
        beds = item.get('bedrooms')
        if beds is not None:
            parts.append('Studio' if beds == 0 else f'{beds} bedroom')
        if item.get('bathrooms'):
            parts.append(f"{item['bathrooms']} bath")
        if item.get('yearBuilt'):
            parts.append(f"Built {item['yearBuilt']}")
        if item.get('daysOnMarket') is not None:
            parts.append(f"{item['daysOnMarket']} days on market")
        summary = ' · '.join(parts)
        city = item.get('city', '')
        ptype = item.get('propertyType', 'Property')
        return f"{ptype}{' in ' + city if city else ''}. {summary}".strip('. ')
