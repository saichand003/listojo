"""
Fill the two listing amenity catalogues from the legacy `tags` column.

    python manage.py backfill_listing_amenities            # only empty rows
    python manage.py backfill_listing_amenities --dry-run
    python manage.py backfill_listing_amenities --overwrite

Listings predate the split: everything a seller ticked in the create form went
into one `tags` string, mixing shared facilities, in-unit features and lease
terms. The vocabulary is small and fixed, so the split can be recovered — see
listings.services.amenities for which tag lands where and why some land nowhere.

`tags` is left untouched. It is the search filter and the tag index is built on
it; this command only populates the display columns beside it, so a row that is
backfilled and a row a seller fills in by hand end up the same shape.

Only rows with both catalogues empty are written, so re-running is safe and a
hand-edited row is never clobbered. `--overwrite` reclassifies everything,
which is what to run after editing the vocabulary.
"""
from django.core.management.base import BaseCommand

from listings.models import Listing
from listings.services.amenities import classify_tags

_FIELDS = ['community_amenities', 'in_unit_amenities']


class Command(BaseCommand):
    help = 'Populate listing amenity catalogues from the legacy tags column.'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true',
                            help='Report what would change without writing.')
        parser.add_argument('--overwrite', action='store_true',
                            help='Reclassify rows that already have catalogue data.')

    def handle(self, *args, **opts):
        qs = Listing.objects.exclude(tags='')
        if not opts['overwrite']:
            qs = qs.filter(community_amenities='', in_unit_amenities='')

        changed, skipped = [], 0
        for listing in qs:
            shared, private = classify_tags(listing.tags.split(','))
            if not shared and not private:
                skipped += 1
                continue
            shared_str, private_str = ', '.join(shared), ', '.join(private)
            if (listing.community_amenities, listing.in_unit_amenities) == (shared_str, private_str):
                skipped += 1
                continue
            listing.community_amenities = shared_str
            listing.in_unit_amenities = private_str
            changed.append(listing)

        for listing in changed:
            self.stdout.write(
                f'  #{listing.pk} {listing.title[:40]}\n'
                f'      {listing.shared_amenities_label}: {listing.community_amenities or "—"}\n'
                f'      {listing.unit_amenities_label}: {listing.in_unit_amenities or "—"}'
            )

        if opts['dry_run']:
            self.stdout.write(self.style.WARNING(
                f'\nDry run — {len(changed)} row(s) would change, {skipped} left alone.'))
            return

        # bulk_update, not save(), to skip the pre_save geocoding signal: these
        # rows have not moved and must not trigger a Google lookup.
        Listing.objects.bulk_update(changed, _FIELDS)
        self.stdout.write(self.style.SUCCESS(
            f'\nBackfilled {len(changed)} listing(s), {skipped} left alone.'))
