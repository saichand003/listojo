"""
Fetch Walk Score / Transit Score / Bike Score for geocoded listings.

    python manage.py fetch_walk_scores                # only missing or stale rows
    python manage.py fetch_walk_scores --force        # refetch everything
    python manage.py fetch_walk_scores --limit 100    # cap API calls this run
    python manage.py fetch_walk_scores --dry-run

Only rows that already have coordinates are eligible — run `geocode_listings`
first if scores come back as "0 candidate row(s)" unexpectedly.
"""
import time

from itertools import chain

from django.core.management.base import BaseCommand

from listings.models import Community, Listing
from listings.services.walkscore import is_stale, score_instance

_FIELDS = [
    'walk_score', 'walk_score_description',
    'transit_score', 'transit_description',
    'bike_score', 'bike_description',
    'walk_score_link', 'walk_score_updated',
]


class Command(BaseCommand):
    help = 'Populate Walk Score data for listings that already have coordinates.'

    def add_arguments(self, parser):
        parser.add_argument('--force', action='store_true',
                            help='Refetch rows that already have a fresh score.')
        parser.add_argument('--limit', type=int, default=0,
                            help='Max number of rows to fetch this run (0 = no limit).')
        parser.add_argument('--sleep', type=float, default=0.2,
                            help='Seconds to pause between API calls (rate-limit safety).')
        parser.add_argument('--dry-run', action='store_true',
                            help='Report what would be fetched without saving.')

    def handle(self, *args, **opts):
        force, limit = opts['force'], opts['limit']
        sleep, dry = opts['sleep'], opts['dry_run']

        # Communities are scored from their own centroid, the same way a
        # listing is — see ProximityDisplayMixin for why the two stay in step.
        rows = chain(Listing.objects.filter(latitude__isnull=False, longitude__isnull=False).iterator(),
                     Community.objects.filter(latitude__isnull=False, longitude__isnull=False).iterator())
        candidates = [obj for obj in rows if force or is_stale(obj)]

        self.stdout.write(f'\nListings + communities: {len(candidates)} candidate row(s)')

        processed = 0
        succeeded = 0
        for obj in candidates:
            if limit and processed >= limit:
                self.stdout.write(self.style.WARNING(f'Reached limit ({limit}). Stopping.'))
                break

            if dry:
                self.stdout.write(f'  [dry] would fetch #{obj.pk}: {obj.full_address}')
                processed += 1
                continue

            processed += 1
            if score_instance(obj, force=force):
                obj.save(update_fields=_FIELDS)
                succeeded += 1
                self.stdout.write(self.style.SUCCESS(
                    f'  ✓ #{obj.pk} walk {obj.walk_score} ({obj.walk_score_description}) · '
                    f'transit {obj.transit_score} · bike {obj.bike_score}  {obj.full_address}'))
            else:
                self.stdout.write(self.style.WARNING(
                    f'  ✗ #{obj.pk} no score returned: {obj.full_address}'))

            if sleep:
                time.sleep(sleep)

        self.stdout.write(self.style.SUCCESS(
            f'\nDone. Scored {succeeded}/{processed} attempted row(s).'))
