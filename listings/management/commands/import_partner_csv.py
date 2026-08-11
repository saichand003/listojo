"""
Import a property manager's inventory from a Listojo CSV export.

    python manage.py import_partner_csv acme inventory.csv
    python manage.py import_partner_csv acme inventory.csv --dry-run
    python manage.py import_partner_csv acme inventory.csv --limit 20
    python manage.py import_partner_csv acme inventory.csv --no-images

The first argument is an Organization slug. Inventory belongs to the company,
not to a person, so rows are attributed to the org's owner-role member unless
`--owner` overrides it. Re-running updates that org's rows and reconciles what
the new file omits — it never duplicates.

Communities resolve through SourceRecordMap, so a property that changed managers
is recognized rather than imported a second time.

Template: docs/partner-csv-template.csv
"""
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError

from listings.services.partner_import import (
    DEFAULT_DEACTIVATION_CEILING,
    CsvAdapter,
    import_partner_inventory,
)
from partners.models import Organization

_MAX_REJECTIONS_SHOWN = 20


class Command(BaseCommand):
    help = "Import a partner's rental inventory from a Listojo-template CSV file."

    def add_arguments(self, parser):
        parser.add_argument('organization',
                            help='Organization slug, e.g. "acme".')
        parser.add_argument('csv_path', help='Path to the partner CSV file.')
        parser.add_argument('--owner', default='',
                            help='Username or email to attribute rows to. Defaults to the '
                                 "organization's owner-role member.")
        parser.add_argument('--status', default='active',
                            choices=['active', 'pending', 'draft'],
                            help='Status for imported rows (default: active).')
        parser.add_argument('--limit', type=int, default=0,
                            help='Import at most N rows (0 = no limit). '
                                 'Skips deactivation, since the file is knowingly partial.')
        parser.add_argument('--dry-run', action='store_true',
                            help='Report what would change without writing.')
        parser.add_argument('--no-images', action='store_true',
                            help='Skip photo download.')
        # No literal '%' in help text — argparse %-formats these strings.
        parser.add_argument('--deactivation-ceiling', type=float,
                            default=DEFAULT_DEACTIVATION_CEILING,
                            help='Abort if the file omits more than this fraction of the '
                                 f"partner's live rows (default: {DEFAULT_DEACTIVATION_CEILING}).")

    def handle(self, *args, **opts):
        organization = self._resolve_organization(opts['organization'])
        owner = self._resolve_owner(opts['owner']) if opts['owner'] else None

        try:
            handle = open(opts['csv_path'], newline='', encoding='utf-8-sig')
        except OSError as exc:
            raise CommandError(f'Could not open {opts["csv_path"]}: {exc}')

        with handle:
            result = import_partner_inventory(
                CsvAdapter(handle),
                organization=organization,
                owner=owner,
                status=opts['status'],
                limit=opts['limit'],
                dry_run=opts['dry_run'],
                fetch_photos=not opts['no_images'],
                deactivation_ceiling=opts['deactivation_ceiling'],
            )

        self._report(result, dry_run=opts['dry_run'])

        if not result.ok:
            raise CommandError(result.aborted_reason)

    def _resolve_organization(self, slug):
        organization = Organization.objects.filter(slug=slug).first()
        if not organization:
            known = ', '.join(Organization.objects.values_list('slug', flat=True)) or 'none yet'
            raise CommandError(
                f'No organization with slug "{slug}". Known slugs: {known}. '
                f'Create one in the admin under Partners → Organizations.')
        return organization

    def _resolve_owner(self, identifier):
        owner = (User.objects.filter(username=identifier).first()
                 or User.objects.filter(email__iexact=identifier).first())
        if not owner:
            raise CommandError(f'No user matches "{identifier}" (tried username and email).')
        return owner

    def _report(self, result, *, dry_run):
        prefix = '[dry run] ' if dry_run else ''

        if result.rejections:
            self.stdout.write(self.style.WARNING(
                f'\n{len(result.rejections)} row(s) rejected:'))
            for rejection in result.rejections[:_MAX_REJECTIONS_SHOWN]:
                where = f'row {rejection.row_number}' if rejection.row_number else 'file'
                self.stdout.write(f'  {where}: {rejection.reason}')
            if len(result.rejections) > _MAX_REJECTIONS_SHOWN:
                self.stdout.write(
                    f'  … and {len(result.rejections) - _MAX_REJECTIONS_SHOWN} more')

        if not result.ok:
            self.stdout.write(self.style.ERROR(f'\n{result.summary()}'))
            return

        self.stdout.write(self.style.SUCCESS(f'\n{prefix}{result.summary()}'))

        if result.pending_deactivation:
            self.stdout.write(
                f'\n{result.pending_deactivation} listing(s) were absent from this file and '
                f'are now pending deactivation.\nThey stay visible until a second import '
                f'also omits them — so a truncated upload can be corrected by re-sending '
                f'the full file.')
