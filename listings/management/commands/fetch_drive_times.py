"""
Fetch typical driving times for listings that already have proximity data.

    python manage.py fetch_drive_times              # only missing or stale rows
    python manage.py fetch_drive_times --force      # refetch everything
    python manage.py fetch_drive_times --limit 100  # cap API calls this run
    python manage.py fetch_drive_times --dry-run

Run this AFTER `assign_downtowns` and `fetch_groceries` — it fills in times for
whatever those two have already matched, and does nothing for a listing with no
downtown and no grocery rows.

Costs one Routes call per listing, covering its downtown and every grocery row
together. Billing is per element (destination), so a listing with a downtown and
five stores is six elements in one request.
"""
import time

from itertools import chain

from django.core.management.base import BaseCommand
from django.db.models import Q

from listings.models import Community, Listing
from listings.services.drivetime import is_stale, sync_instance


class Command(BaseCommand):
    help = 'Populate drive times for listings with a downtown or grocery rows.'

    def add_arguments(self, parser):
        parser.add_argument('--force', action='store_true',
                            help='Refetch rows whose times are still fresh.')
        parser.add_argument('--limit', type=int, default=0,
                            help='Max number of rows to fetch this run (0 = no limit).')
        parser.add_argument('--sleep', type=float, default=0.2,
                            help='Seconds to pause between API calls (rate-limit safety).')
        parser.add_argument('--dry-run', action='store_true',
                            help='Report what would be fetched without saving.')

    def handle(self, *args, **opts):
        force, limit = opts['force'], opts['limit']
        sleep, dry = opts['sleep'], opts['dry_run']

        # Only listings with something to measure against — anything else would
        # be a wasted call.
        # Communities are scored from their own centroid, the same way a
        # listing is — see ProximityDisplayMixin for why the two stay in step.
        has_targets = Q(nearest_downtown__isnull=False) | Q(nearby_groceries__isnull=False)
        rows = chain(
            Listing.objects.filter(latitude__isnull=False, longitude__isnull=False).filter(has_targets).distinct().iterator(),
            Community.objects.filter(latitude__isnull=False, longitude__isnull=False).filter(has_targets).distinct().iterator(),
        )
        candidates = [obj for obj in rows if force or is_stale(obj)]

        self.stdout.write(
            f'\nListings + communities: {len(candidates)} candidate row(s) with proximity data')

        processed = succeeded = 0
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
                    f'  ✓ #{obj.pk} {count} drive time(s)  {obj.full_address}'))
            elif count == 0:
                succeeded += 1
                self.stdout.write(f'  · #{obj.pk} no drivable routes: {obj.full_address}')
            else:
                self.stdout.write(self.style.WARNING(
                    f'  ✗ #{obj.pk} lookup failed: {obj.full_address}'))

            if sleep:
                time.sleep(sleep)

        self.stdout.write(self.style.SUCCESS(
            f'\nDone. Synced {succeeded}/{processed} attempted row(s).'))
