"""
Match geocoded listings to nearby transit stations and compute Commute Scores.

    python manage.py fetch_transit                 # only missing or stale rows
    python manage.py fetch_transit --force         # rematch everything
    python manage.py fetch_transit --score-only    # recompute scores, skip matching
    python manage.py fetch_transit --limit 100
    python manage.py fetch_transit --dry-run

Only rows that already have coordinates are eligible — run `geocode_listings`
first if this reports "0 candidate row(s)" unexpectedly.

Unlike `fetch_groceries`, nothing here calls a paid API: stations come from the
GTFS import and the distance is local maths, so `--limit` is about run time, not
spend. Run `import_gtfs` first, and re-run this with `--force` after any import
that changed the station table.

Ordering matters for the score. The downtown drive is one of its four
components, so the full sequence is:

    geocode_listings → assign_downtowns → fetch_transit → fetch_drive_times
                     → fetch_transit --score-only

The last pass exists because `fetch_drive_times` is what fills in
downtown_drive_minutes; scoring before it runs simply leaves that component at
zero, which is a real answer for an unmeasured listing but not the final one.
"""
from django.core.management.base import BaseCommand

from listings.models import Listing
from listings.services.commute_score import assign_instance
from listings.services.transit import is_stale, sync_instance


class Command(BaseCommand):
    help = 'Match listings to nearby transit stations and compute Commute Scores.'

    def add_arguments(self, parser):
        parser.add_argument('--force', action='store_true',
                            help='Rematch rows whose stations are still fresh.')
        parser.add_argument('--score-only', action='store_true',
                            help='Recompute scores from existing matches without rematching.')
        parser.add_argument('--limit', type=int, default=0,
                            help='Max number of rows to process this run (0 = no limit).')
        parser.add_argument('--dry-run', action='store_true',
                            help='Report what would change without saving.')

    def handle(self, *args, **opts):
        force, limit = opts['force'], opts['limit']
        score_only, dry = opts['score_only'], opts['dry_run']

        qs = Listing.objects.filter(latitude__isnull=False, longitude__isnull=False)
        if score_only:
            # Only rows that have actually been matched can be scored; the rest
            # would score None and rewrite nothing.
            candidates = list(qs.filter(transit_updated__isnull=False))
        else:
            candidates = [obj for obj in qs.iterator() if force or is_stale(obj)]

        self.stdout.write(f'\nListing: {len(candidates)} candidate row(s) with coordinates')

        processed = matched = scored = 0
        for obj in candidates:
            if limit and processed >= limit:
                self.stdout.write(self.style.WARNING(f'Reached limit ({limit}). Stopping.'))
                break
            processed += 1

            if dry:
                self.stdout.write(f'  [dry] would process #{obj.pk}: {obj.full_address}')
                continue

            if not score_only:
                count = sync_instance(obj, force=force)
                if count:
                    matched += 1
                    names = ', '.join(
                        f'{l.station.name}'
                        f'{" [" + "/".join(r.label for r in l.station.route_badges) + "]" if l.station.route_badges else ""}'
                        for l in obj.transit_cards)
                    self.stdout.write(self.style.SUCCESS(
                        f'  ✓ #{obj.pk} {count} station(s): {names}'))
                elif count == 0:
                    # Distinct from a failure: the scan worked, nothing in range.
                    self.stdout.write(f'  · #{obj.pk} no stations in range: {obj.full_address}')
                else:
                    self.stdout.write(self.style.WARNING(
                        f'  ✗ #{obj.pk} not matched (no coordinates?): {obj.full_address}'))

            # Refetch so the score reads the links sync_instance just wrote
            # rather than a queryset cached before them.
            obj.refresh_from_db()
            score = assign_instance(obj)
            obj.save(update_fields=['commute_score', 'commute_score_label'])
            if score is not None:
                scored += 1
                self.stdout.write(f'      Commute Score {score} — {obj.commute_score_label}')

        self.stdout.write(self.style.SUCCESS(
            f'\nDone. Matched {matched}, scored {scored} of {processed} row(s).'))
