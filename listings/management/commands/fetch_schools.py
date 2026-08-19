"""
Fetch nearby GreatSchools data for geocoded listings.

    python manage.py fetch_schools                # only missing or stale rows
    python manage.py fetch_schools --force        # refetch everything
    python manage.py fetch_schools --limit 100    # cap API calls this run
    python manage.py fetch_schools --dry-run

Only rows that already have coordinates are eligible — run `geocode_listings`
first if this reports "0 candidate row(s)" unexpectedly.

Responses are cached per coordinate grid square (see services.greatschools), so
a community whose units share an address costs one API call, not one per unit.
"""
import time

from django.core.management.base import BaseCommand

from listings.models import Listing
from listings.services.greatschools import is_stale, sync_instance


class Command(BaseCommand):
    help = 'Populate nearby school data for listings that already have coordinates.'

    def add_arguments(self, parser):
        parser.add_argument('--force', action='store_true',
                            help='Refetch rows whose schools are still fresh.')
        parser.add_argument('--limit', type=int, default=0,
                            help='Max number of rows to fetch this run (0 = no limit).')
        parser.add_argument('--sleep', type=float, default=0.2,
                            help='Seconds to pause between API calls (rate-limit safety).')
        parser.add_argument('--dry-run', action='store_true',
                            help='Report what would be fetched without saving.')

    def handle(self, *args, **opts):
        force, limit = opts['force'], opts['limit']
        sleep, dry = opts['sleep'], opts['dry_run']

        qs = Listing.objects.filter(latitude__isnull=False, longitude__isnull=False)
        candidates = [obj for obj in qs.iterator() if force or is_stale(obj)]

        self.stdout.write(f'\nListing: {len(candidates)} candidate row(s) with coordinates')

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
            count = sync_instance(obj, force=force)
            if count:
                succeeded += 1
                self.stdout.write(self.style.SUCCESS(
                    f'  ✓ #{obj.pk} {count} school(s)  {obj.full_address}'))
            elif count == 0:
                # Distinct from a failure: the lookup worked, the area is empty.
                succeeded += 1
                self.stdout.write(f'  · #{obj.pk} no schools in range: {obj.full_address}')
            else:
                self.stdout.write(self.style.WARNING(
                    f'  ✗ #{obj.pk} lookup failed: {obj.full_address}'))

            if sleep:
                time.sleep(sleep)

        self.stdout.write(self.style.SUCCESS(
            f'\nDone. Synced {succeeded}/{processed} attempted row(s).'))
