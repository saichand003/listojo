"""
Match every geocoded listing to its nearest downtown.

    python manage.py assign_downtowns
    python manage.py assign_downtowns --dry-run

No API is involved — this is local maths over the Downtown table — so it is
cheap to re-run, and it must be re-run after `seed_downtowns` adds a metro or
after listings are geocoded.

Only rows that already have coordinates are eligible; run `geocode_listings`
first if this reports "0 candidate row(s)" unexpectedly.
"""
from django.core.management.base import BaseCommand

from listings.models import Listing
from listings.services.downtowns import assign_instance

_FIELDS = ['nearest_downtown', 'downtown_distance_miles']


class Command(BaseCommand):
    help = 'Set nearest_downtown / downtown_distance_miles on geocoded listings.'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true',
                            help='Report what would change without saving.')

    def handle(self, *args, **opts):
        dry = opts['dry_run']
        qs = Listing.objects.filter(latitude__isnull=False, longitude__isnull=False)
        total = qs.count()

        self.stdout.write(f'\nListing: {total} candidate row(s) with coordinates')

        matched = unmatched = 0
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

            if not dry:
                obj.save(update_fields=_FIELDS)

        self.stdout.write(self.style.SUCCESS(
            f'\nDone. Matched {matched}, unmatched {unmatched}.'))
