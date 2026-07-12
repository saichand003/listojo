"""
Resend HTTP-API email backend.

Cloud hosts (Railway, Render, etc.) often block outbound SMTP ports, so SMTP
sends silently time out and never reach Resend. This backend sends over HTTPS
(port 443) via Resend's REST API instead — same send_mail() interface, no SMTP.

Enable with:
    EMAIL_BACKEND=listojo.email_backends.ResendEmailBackend
    RESEND_API_KEY=re_xxx           (falls back to EMAIL_HOST_PASSWORD)
    DEFAULT_FROM_EMAIL=Listojo <onboarding@resend.dev>
"""
from __future__ import annotations

import logging

import requests
from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend

logger = logging.getLogger(__name__)

_API_URL = 'https://api.resend.com/emails'
_TIMEOUT = 10


class ResendEmailBackend(BaseEmailBackend):
    def _api_key(self) -> str:
        return getattr(settings, 'RESEND_API_KEY', '') or getattr(settings, 'EMAIL_HOST_PASSWORD', '')

    def send_messages(self, email_messages) -> int:
        if not email_messages:
            return 0
        api_key = self._api_key()
        if not api_key:
            logger.warning('ResendEmailBackend: no API key configured')
            if not self.fail_silently:
                raise RuntimeError('RESEND_API_KEY / EMAIL_HOST_PASSWORD is not set')
            return 0

        headers = {'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'}
        sent = 0
        for msg in email_messages:
            payload = {
                'from': msg.from_email or settings.DEFAULT_FROM_EMAIL,
                'to': list(msg.to),
                'subject': msg.subject,
                'text': msg.body or '',
            }
            if msg.cc:
                payload['cc'] = list(msg.cc)
            if msg.bcc:
                payload['bcc'] = list(msg.bcc)
            if msg.reply_to:
                payload['reply_to'] = list(msg.reply_to)
            # HTML alternative, if any (EmailMultiAlternatives)
            for content, mimetype in getattr(msg, 'alternatives', []) or []:
                if mimetype == 'text/html':
                    payload['html'] = content
                    break

            try:
                resp = requests.post(_API_URL, headers=headers, json=payload, timeout=_TIMEOUT)
                if resp.status_code in (200, 201):
                    sent += 1
                else:
                    logger.warning('Resend API %s: %s', resp.status_code, resp.text[:300])
                    if not self.fail_silently:
                        raise RuntimeError(f'Resend API error {resp.status_code}: {resp.text[:300]}')
            except requests.RequestException as exc:
                logger.exception('Resend API request failed')
                if not self.fail_silently:
                    raise RuntimeError(f'Resend API request failed: {exc}') from exc
        return sent
