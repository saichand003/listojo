"""
Verify email delivery end-to-end.

    python manage.py send_test_email you@example.com

Prints the active backend + config, sends a test message, and reports success
or the exact error. Use this right after setting your SMTP env vars.
"""
from django.conf import settings
from django.core.mail import send_mail
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = 'Send a test email to confirm SMTP is configured correctly.'

    def add_arguments(self, parser):
        parser.add_argument('to', help='Recipient email address')

    def handle(self, *args, **opts):
        to = opts['to']
        self.stdout.write('Email config:')
        self.stdout.write(f'  BACKEND = {settings.EMAIL_BACKEND}')
        self.stdout.write(f'  HOST    = {settings.EMAIL_HOST}:{settings.EMAIL_PORT} (TLS={settings.EMAIL_USE_TLS})')
        self.stdout.write(f'  USER    = {settings.EMAIL_HOST_USER or "(empty)"}')
        self.stdout.write(f'  FROM    = {settings.DEFAULT_FROM_EMAIL}')

        if 'console' in settings.EMAIL_BACKEND:
            self.stdout.write(self.style.WARNING(
                '\n⚠ Using the CONSOLE backend — the message below is printed, not delivered.\n'
                '  Set EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend to send for real.\n'))

        try:
            sent = send_mail(
                subject='Listojo email test ✓',
                message='If you can read this in your inbox, SMTP is working.',
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[to],
                fail_silently=False,
            )
        except Exception as exc:  # noqa: BLE001
            raise CommandError(f'Send failed: {exc!r}')

        if sent:
            self.stdout.write(self.style.SUCCESS(f'\n✓ Sent to {to}. Check the inbox (and spam).'))
        else:
            self.stdout.write(self.style.ERROR('\n✗ send_mail returned 0 — nothing sent.'))
