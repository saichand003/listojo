"""
Ask community owners "still available?" and hide units nobody vouches for.

    python manage.py send_availability_checks
    python manage.py send_availability_checks --dry-run

Scheduled daily alongside send_saved_search_alerts (railway.cron.json). The
timeline — ask at 14 days, hide 7 days later — lives in
listings/services/availability_checks.py.
"""
from django.conf import settings
from django.core.management.base import BaseCommand

from listings.services.availability_checks import run_availability_checks


class Command(BaseCommand):
    help = 'Email community owners to confirm availability; hide units left unconfirmed.'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true',
                            help='Report who would be asked or hidden without sending or saving.')
        parser.add_argument(
            '--site-url', default='',
            help='Absolute base URL for links (defaults to settings.SITE_URL or https://listojo.com).',
        )

    def handle(self, *args, **opts):
        site_url = (opts['site_url']
                    or getattr(settings, 'SITE_URL', '')
                    or 'https://listojo.com').rstrip('/')

        result = run_availability_checks(site_url, dry_run=opts['dry_run'])
        prefix = '[dry run] ' if opts['dry_run'] else ''
        for community in result.hidden:
            self.stdout.write(f'{prefix}hid units: {community.name} (#{community.pk})')
        for community in result.asked:
            self.stdout.write(f'{prefix}asked: {community.name} (#{community.pk})')
        self.stdout.write(self.style.SUCCESS(
            f'{prefix}Asked {len(result.asked)} owner(s); '
            f'hid units at {len(result.hidden)} community(ies).'))
