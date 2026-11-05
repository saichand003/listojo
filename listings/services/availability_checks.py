"""
Stale-listing control for communities.

Every ~14 days an owner is asked "still available?". No confirmation within a
week hides their units — the community page and its lead form stay up, every
floor plan just reads "contact for availability" — until they confirm.

    day 0    owner confirms (link, edit-page button, unit edit, partner upload)
    day 14   "still available?" email, confirmation_requested_at = now
    day 21   no reply → availability_hidden_at = now, units drop off the page

Later, ILS feed polling will write the same status fields, and a successful
poll will count as a confirmation the way a partner CSV upload already does.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import timedelta

from django.conf import settings
from django.core import signing
from django.core.mail import send_mail
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone

logger = logging.getLogger(__name__)

CONFIRM_EVERY = timedelta(days=14)
GRACE_PERIOD = timedelta(days=7)
#: A link outlives one cycle so a late reply still works, but not forever.
TOKEN_MAX_AGE = timedelta(days=30)

_SALT = 'listings.community-availability'


@dataclass
class CheckResult:
    asked: list = field(default_factory=list)
    hidden: list = field(default_factory=list)


# ─────────────────────────────────────────────────────────────────────────────
# Confirm links
# ─────────────────────────────────────────────────────────────────────────────

def confirm_token(community) -> str:
    return signing.TimestampSigner(salt=_SALT).sign(str(community.pk))


def community_for_token(token: str):
    """The community a confirm link names, or None if it is forged or expired."""
    from listings.models import Community

    try:
        pk = signing.TimestampSigner(salt=_SALT).unsign(
            token, max_age=TOKEN_MAX_AGE.total_seconds())
    except signing.BadSignature:
        return None
    return Community.objects.filter(pk=int(pk)).first()


def confirm_url(community, site_url: str) -> str:
    return site_url + reverse('confirm_availability_link', args=[confirm_token(community)])


# ─────────────────────────────────────────────────────────────────────────────
# The scheduled job
# ─────────────────────────────────────────────────────────────────────────────

def run_availability_checks(site_url: str, *, now=None, dry_run: bool = False) -> CheckResult:
    """Hide what went unconfirmed, then ask whoever is due. Safe to run hourly."""
    from listings.models import Community

    now = now or timezone.now()
    result = CheckResult()
    live = Community.objects.filter(status='active').select_related('owner')

    # Hide first, so a community asked today is never also hidden today.
    overdue = live.filter(
        availability_hidden_at__isnull=True,
        confirmation_requested_at__lte=now - GRACE_PERIOD,
    )
    for community in overdue:
        result.hidden.append(community)
        if dry_run:
            continue
        community.availability_hidden_at = now
        community.save(update_fields=['availability_hidden_at'])
        _send(community, _hidden_message(community, site_url))

    due = live.filter(
        Q(confirmation_requested_at__isnull=True),
        last_confirmed_at__lte=now - CONFIRM_EVERY,
    )
    for community in due:
        if not _recipient(community):
            # Nobody to ask. Hiding a community for an email it could never
            # receive would punish a data-entry gap; staff see it in the log.
            logger.warning('Availability check skipped for community %s: no email', community.pk)
            continue
        result.asked.append(community)
        if dry_run:
            continue
        community.confirmation_requested_at = now
        community.save(update_fields=['confirmation_requested_at'])
        _send(community, _ask_message(community, site_url))

    return result


def _recipient(community) -> str:
    return community.contact_email or (community.owner.email if community.owner else '')


def _send(community, message: tuple[str, str]) -> None:
    subject, body = message
    send_mail(subject=subject, message=body,
              from_email=settings.DEFAULT_FROM_EMAIL,
              recipient_list=[_recipient(community)], fail_silently=True)


def _unit_lines(community) -> list[str]:
    from listings.models import Unit

    units = (Unit.objects.filter(floor_plan__community=community)
             .exclude(status__in=(Unit.LEASED, Unit.OFF_MARKET))
             .select_related('floor_plan')
             .order_by('floor_plan__bedrooms', 'unit_number'))
    lines = []
    for unit in units:
        price = f'${unit.price:,.0f}/mo' if unit.price else 'price not set'
        when = (f'from {unit.available_from:%b %-d}' if unit.available_from
                else 'now')
        lines.append(f'  • {unit.floor_plan.name} — Unit {unit.unit_number}: '
                     f'{unit.get_status_display()}, {price}, {when}')
    return lines or ['  (no available or coming-soon units listed)']


def _greeting(community) -> str:
    name = (community.owner.first_name or community.owner.username) if community.owner else ''
    return f'Hi {name},' if name else 'Hi,'


def _ask_message(community, site_url: str) -> tuple[str, str]:
    edit_url = site_url + reverse('edit_community', args=[community.pk])
    body = '\n'.join([
        _greeting(community),
        '',
        f'Are these units at {community.name} still available?',
        '',
        *_unit_lines(community),
        '',
        f'If this is right, confirm with one click:\n{confirm_url(community, site_url)}',
        '',
        f'If anything changed (leased, new price, new move-in date), update it here:\n{edit_url}',
        '',
        f'If we do not hear back within {GRACE_PERIOD.days} days, we will hide these units '
        'from renters so nobody tours a unit that is gone. Your community page stays up.',
        '',
        '— Listojo',
    ])
    return f'Still available? Confirm your units at {community.name}', body


def _hidden_message(community, site_url: str) -> tuple[str, str]:
    body = '\n'.join([
        _greeting(community),
        '',
        f'We did not hear back about {community.name}, so its units are now hidden '
        'from renters. The community page and tour requests still work.',
        '',
        f'Confirm your availability to show them again:\n{confirm_url(community, site_url)}',
        '',
        '— Listojo',
    ])
    return f'Units hidden at {community.name} — confirm to show them again', body
