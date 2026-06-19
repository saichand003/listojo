"""
Backfill real lat/lng for existing listings and communities.

    python manage.py geocode_listings                # only rows missing coords
    python manage.py geocode_listings --force         # re-geocode everything
    python manage.py geocode_listings --limit 100     # cap API calls this run
    python manage.py geocode_listings --model listings --dry-run
"""
import time

from django.core.management.base import BaseCommand

from listings.models import Community, Listing
from listings.services.geocoding import geocode_instance


class Command(BaseCommand):
    help = 'Geocode existing Listings and Communities into real lat/lng coordinates.'

    def add_arguments(self, parser):
        parser.add_argument('--force', action='store_true',
                            help='Re-geocode rows that already have coordinates.')
        parser.add_argument('--limit', type=int, default=0,
                            help='Max number of rows to geocode this run (0 = no limit).')
        parser.add_argument('--model', choices=['listings', 'communities', 'all'], default='all')
        parser.add_argument('--sleep', type=float, default=0.05,
                            help='Seconds to pause between API calls (rate-limit safety).')
        parser.add_argument('--dry-run', action='store_true',
                            help='Report what would be geocoded without saving.')

    def handle(self, *args, **opts):
        force, limit = opts['force'], opts['limit']
        sleep, dry = opts['sleep'], opts['dry_run']
        which = opts['model']

        targets = []
        if which in ('listings', 'all'):
            targets.append(('Listing', Listing))
        if which in ('communities', 'all'):
            targets.append(('Community', Community))

        processed = 0   # rows attempted (caps API spend via --limit)
        succeeded = 0
        for label, Model in targets:
            qs = Model.objects.all()
            if not force:
                qs = qs.filter(latitude__isnull=True)

            self.stdout.write(f'\n{label}: {qs.count()} candidate row(s)')
            for obj in qs.iterator():
                if limit and processed >= limit:
                    self.stdout.write(self.style.WARNING(f'Reached limit ({limit}). Stopping.'))
                    self.stdout.write(self.style.SUCCESS(
                        f'\nDone. Geocoded {succeeded}/{processed} attempted row(s).'))
                    return

                addr = obj.full_address
                if not addr:
                    continue

                if dry:
                    self.stdout.write(f'  [dry] would geocode #{obj.pk}: {addr}')
                    processed += 1
                    continue

                processed += 1
                ok = geocode_instance(obj, force=force)
                if ok:
                    obj.save(update_fields=['latitude', 'longitude', 'geocoded_address'])
                    succeeded += 1
                    self.stdout.write(self.style.SUCCESS(
                        f'  ✓ #{obj.pk} → ({obj.latitude}, {obj.longitude})  {addr}'))
                else:
                    self.stdout.write(self.style.WARNING(f'  ✗ #{obj.pk} could not geocode: {addr}'))

                if sleep:
                    time.sleep(sleep)

        self.stdout.write(self.style.SUCCESS(
            f'\nDone. Geocoded {succeeded}/{processed} attempted row(s).'))
