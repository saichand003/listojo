"""
Send the daily new-match digest (email + SMS) for every saved guided search.

    python manage.py send_saved_search_alerts
    python manage.py send_saved_search_alerts --site-url https://listojo.com

Scheduled daily by the `listojo-cron` Railway service (railway.cron.json).
Each search keeps a `last_alerted_at` watermark, so listings are alerted
exactly once, and a search gets at most one digest per day however often this
runs.
"""
from django.conf import settings
from django.core.management.base import BaseCommand

from listings.services.saved_search_alerts import send_alerts_for_all


class Command(BaseCommand):
    help = 'Email/SMS users about new listings matching their saved searches.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--site-url', default='',
            help='Absolute base URL for links (defaults to settings.SITE_URL or https://listojo.com).',
        )

    def handle(self, *args, **opts):
        site_url = (opts['site_url']
                    or getattr(settings, 'SITE_URL', '')
                    or 'https://listojo.com').rstrip('/')

        result = send_alerts_for_all(site_url)
        self.stdout.write(self.style.SUCCESS(
            f"Processed {result['searches']} search(es): "
            f"notified {result['notified']} user(s) about {result['listings']} listing(s)."
        ))
