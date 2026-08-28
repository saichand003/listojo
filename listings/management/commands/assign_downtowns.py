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

from itertools import chain

from listings.models import Community, Listing
from listings.services.downtowns import assign_instance

_FIELDS = ['nearest_downtown', 'downtown_distance_miles']

# Rows are written with bulk_update rather than save(), specifically to skip the
# pre_save geocoding signal. That signal short-circuits for an already-geocoded
# row, but a row whose address changed without a re-geocode would call Google —
# and this command runs on every container boot.
_BATCH_SIZE = 500


def _flush(rows):
    """Write a mixed batch back, one bulk_update per model."""
    by_model = {}
    for obj in rows:
        by_model.setdefault(type(obj), []).append(obj)
    for model, batch in by_model.items():
        model.objects.bulk_update(batch, _FIELDS, batch_size=_BATCH_SIZE)


class Command(BaseCommand):
    help = 'Set nearest_downtown / downtown_distance_miles on geocoded listings.'

    def add_arguments(self, parser):
        parser.add_argument('--missing-only', action='store_true',
                            help='Only process listings that have no downtown yet.')
        parser.add_argument('--dry-run', action='store_true',
                            help='Report what would change without saving.')

    def handle(self, *args, **opts):
        dry, missing_only = opts['dry_run'], opts['missing_only']

        # Communities get a downtown the same way listings do — the service
        # only ever reads lat/lng off the instance.
        querysets = [Listing.objects.filter(latitude__isnull=False, longitude__isnull=False),
                     Community.objects.filter(latitude__isnull=False, longitude__isnull=False)]
        if missing_only:
            querysets = [qs.filter(nearest_downtown__isnull=True) for qs in querysets]

        scope = 'unassigned' if missing_only else 'geocoded'
        total = sum(qs.count() for qs in querysets)
        self.stdout.write(f'\nListings + communities: {total} {scope} row(s) with coordinates')

        matched = unmatched = 0
        pending = []

        for obj in chain(*[qs.iterator() for qs in querysets]):
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
                _flush(pending)
                pending = []

        if not dry and pending:
            _flush(pending)

        self.stdout.write(self.style.SUCCESS(
            f'\nDone. Matched {matched}, unmatched {unmatched}.'))
