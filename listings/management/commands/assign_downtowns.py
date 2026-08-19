"""
Match every geocoded listing to its nearest downtown.

    python manage.py assign_downtowns                 # recompute all
    python manage.py assign_downtowns --missing-only  # only unassigned rows
    python manage.py assign_downtowns --dry-run

No API is involved — this is local maths over the Downtown table — so a full
run is cheap and safe to repeat. Re-run it after `seed_downtowns` adds a metro,
otherwise existing listings keep pointing at whichever downtown was nearest
before the new one existed.

`--missing-only` is what the deploy runs on boot: it touches nothing once every
listing has a downtown, so restarts stay fast as the table grows.

Only rows that already have coordinates are eligible; run `geocode_listings`
first if this reports "0 candidate row(s)" unexpectedly.
"""
from django.core.management.base import BaseCommand

from listings.models import Listing
from listings.services.downtowns import assign_instance

_FIELDS = ['nearest_downtown', 'downtown_distance_miles']

# Rows are written with bulk_update rather than save(), specifically to skip the
# pre_save geocoding signal. That signal short-circuits for an already-geocoded
# row, but a row whose address changed without a re-geocode would call Google —
# and this command runs on every container boot.
_BATCH_SIZE = 500


class Command(BaseCommand):
    help = 'Set nearest_downtown / downtown_distance_miles on geocoded listings.'

    def add_arguments(self, parser):
        parser.add_argument('--missing-only', action='store_true',
                            help='Only process listings that have no downtown yet.')
        parser.add_argument('--dry-run', action='store_true',
                            help='Report what would change without saving.')

    def handle(self, *args, **opts):
        dry, missing_only = opts['dry_run'], opts['missing_only']

        qs = Listing.objects.filter(latitude__isnull=False, longitude__isnull=False)
        if missing_only:
            qs = qs.filter(nearest_downtown__isnull=True)

        scope = 'unassigned' if missing_only else 'geocoded'
        total = qs.count()
        self.stdout.write(f'\nListing: {total} {scope} row(s) with coordinates')

        matched = unmatched = 0
        pending = []

        for obj in qs.iterator():
            if assign_instance(obj):
                matched += 1
                line = (f'  ✓ #{obj.pk} {obj.nearest_downtown.name} '
                        f'({obj.downtown_distance_miles} mi)  {obj.full_address}')
                self.stdout.write(f'  [dry]{line[3:]}' if dry else self.style.SUCCESS(line))
            else:
                unmatched += 1
                self.stdout.write(self.style.WARNING(
                    f'  ✗ #{obj.pk} no downtown matched: {obj.full_address}'))

            pending.append(obj)
            if not dry and len(pending) >= _BATCH_SIZE:
                Listing.objects.bulk_update(pending, _FIELDS, batch_size=_BATCH_SIZE)
                pending = []

        if not dry and pending:
            Listing.objects.bulk_update(pending, _FIELDS, batch_size=_BATCH_SIZE)

        self.stdout.write(self.style.SUCCESS(
            f'\nDone. Matched {matched}, unmatched {unmatched}.'))
