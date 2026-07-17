"""
Send ONE saved-search alert email to a chosen address, for previewing.

Renders the real Zumper-style template with real listings and delivers it to
whatever address you pass — regardless of listing watermarks or notify prefs.

    # Use a specific user's saved search (falls back to a sample search):
    python manage.py preview_alert_email you@example.com --user alice

    # Or just preview a rent search in a city:
    python manage.py preview_alert_email you@example.com --search-type rent --city "Fort Worth"

Requires a real email backend (Resend) to actually deliver:
    EMAIL_BACKEND=listojo.email_backends.ResendEmailBackend RESEND_API_KEY=re_xxx \
        python manage.py preview_alert_email you@example.com
On Railway those env vars are already set, so no flags are needed there.
"""
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import EmailMultiAlternatives
from django.core.management.base import BaseCommand, CommandError

from listings.models import SavedSearch
from listings.services.saved_search_alerts import (
    _build_alert_bodies, _build_html_body, matching_listings_for_search,
)
from listings.services.visibility import active_listings

User = get_user_model()


class Command(BaseCommand):
    help = 'Send one saved-search alert email to a chosen address for previewing.'

    def add_arguments(self, parser):
        parser.add_argument('to', help='Recipient email address')
        parser.add_argument('--user', default='', help='Username whose saved search to use')
        parser.add_argument('--search-type', default='rent', choices=['rent', 'buy'])
        parser.add_argument('--city', default='', help='City filter for the sample search')
        parser.add_argument('--site-url', default='',
                            help='Base URL for links (defaults to settings.SITE_URL).')

    def handle(self, *args, **opts):
        to = opts['to']
        site_url = (opts['site_url'] or getattr(settings, 'SITE_URL', '')
                    or 'https://listojo.com').rstrip('/')

        # Resolve a SavedSearch: the user's real one, else a sample (unsaved).
        search = None
        if opts['user']:
            try:
                user = User.objects.get(username=opts['user'])
            except User.DoesNotExist:
                raise CommandError(f'No user named {opts["user"]!r}')
            search = SavedSearch.objects.filter(user=user).first()
        if search is None:
            search = SavedSearch(
                user=User.objects.filter(is_superuser=True).first() or User.objects.first(),
                search_type=opts['search_type'],
                city=opts['city'],
            )

        # Current matches; fall back to latest active listings so the preview
        # always has cards even if nothing strictly matches.
        matches = list(matching_listings_for_search(search)[:6])
        if not matches:
            matches = list(active_listings().filter(parent__isnull=True).order_by('-created_at')[:6])
        if not matches:
            raise CommandError('No active listings exist to preview.')

        subject, text_body, _ = _build_alert_bodies(search, matches, site_url)
        html_body = _build_html_body(search, matches, site_url)

        self.stdout.write(f'Backend: {settings.EMAIL_BACKEND}')
        if 'console' in settings.EMAIL_BACKEND:
            self.stdout.write(self.style.WARNING(
                'Console backend active — email is PRINTED below, not delivered. '
                'Set EMAIL_BACKEND=listojo.email_backends.ResendEmailBackend + RESEND_API_KEY to send.'))

        msg = EmailMultiAlternatives(
            subject=subject, body=text_body,
            from_email=settings.DEFAULT_FROM_EMAIL, to=[to],
        )
        msg.attach_alternative(html_body, 'text/html')
        sent = msg.send(fail_silently=False)

        if sent:
            self.stdout.write(self.style.SUCCESS(
                f'Sent preview ({len(matches)} listing(s)) to {to}.'))
        else:
            self.stdout.write(self.style.ERROR('Send returned 0 — not delivered.'))
