"""
Turning a PartnerApplication into a working partner account.

Approving is four facts, not one: the company exists (Organization), a person
may act for it (User + Membership), and the application records what it became.
Done by hand in admin that is four chances to stop halfway, and the halfway
states are silent — an Organization with no Membership locks the partner out of
their own portfolio, and a User with no Membership just sees the 403 page in
`partner_required`. So it is one transaction or nothing.

The invite is deliberately a password *reset* link rather than a generated
password: Listojo never chooses, stores, or emails a partner's credential.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from django.conf import settings
from django.contrib.auth.models import User
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.db import transaction
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from django.utils.text import slugify

from partners.models import Membership, Organization, PartnerApplication

logger = logging.getLogger(__name__)


@dataclass
class ApprovalResult:
    organization: Organization
    user: User
    created_organization: bool
    created_user: bool
    invite_sent: bool
    already_approved: bool = False


def approve_application(application: PartnerApplication) -> ApprovalResult:
    """
    Create the org, the account and the membership, then invite the contact.

    Idempotent: an application already linked to an organization is returned
    untouched and no second invite goes out. Staff double-clicking the admin
    action must not create Acme and Acme-2.
    """
    if application.organization_id:
        organization = application.organization
        return ApprovalResult(
            organization=organization,
            user=organization.owner_user,
            created_organization=False,
            created_user=False,
            invite_sent=False,
            already_approved=True,
        )

    with transaction.atomic():
        organization = Organization.objects.create(
            name=application.company_name,
            slug=_unique_slug(application.company_name),
            status='onboarding',
            contact_name=application.contact_name,
            contact_email=application.contact_email,
            contact_phone=application.contact_phone,
            website=application.website,
        )

        user, created_user = _get_or_create_contact(application)

        # role='owner' — the first person in is the one who can be attributed
        # inventory by a feed. See Organization.owner_user.
        Membership.objects.get_or_create(
            user=user, organization=organization, defaults={'role': 'owner'})

        application.organization = organization
        application.status = 'approved'
        application.save(update_fields=['organization', 'status'])

    # Outside the transaction on purpose: a mail outage must not roll back an
    # account that was created correctly, and the send is network I/O we should
    # not hold a row lock across. Re-running the action re-sends the invite.
    invite_sent = _send_invite(user, organization, is_new_account=created_user)

    return ApprovalResult(
        organization=organization,
        user=user,
        created_organization=True,
        created_user=created_user,
        invite_sent=invite_sent,
    )


def _unique_slug(name: str) -> str:
    """'Oaks Properties' -> 'oaks-properties', or '-2' if that is taken."""
    base = slugify(name)[:70] or 'partner'
    slug = base
    suffix = 2
    while Organization.objects.filter(slug=slug).exists():
        slug = f'{base[:70 - len(str(suffix)) - 1]}-{suffix}'
        suffix += 1
    return slug


def _get_or_create_contact(application: PartnerApplication) -> tuple[User, bool]:
    """
    Reuse an existing account for that email rather than making a second one.

    A property manager who already browsed Listojo as a renter keeps one login.
    Matching is case-insensitive because email is.
    """
    email = application.contact_email.strip()
    existing = User.objects.filter(email__iexact=email).order_by('pk').first()
    if existing:
        return existing, False

    first, _, last = application.contact_name.strip().partition(' ')
    user = User(
        username=_unique_username(email),
        email=email,
        first_name=first[:150],
        last_name=last[:150],
    )
    # No password is ever chosen for them — the invite link sets the first one.
    user.set_unusable_password()
    user.save()
    return user, True


def _unique_username(email: str) -> str:
    """The email is the username: it is what the partner will remember."""
    base = email[:150]
    username = base
    suffix = 2
    while User.objects.filter(username__iexact=username).exists():
        username = f'{base[:150 - len(str(suffix)) - 1]}-{suffix}'
        suffix += 1
    return username


def _send_invite(user: User, organization: Organization, *, is_new_account: bool) -> bool:
    """Password-reset link for a new account, sign-in pointer for an existing one."""
    if not user.email:
        return False

    site = getattr(settings, 'SITE_URL', 'https://listojo.com').rstrip('/')
    greeting = user.first_name or user.get_username()

    if is_new_account:
        path = reverse('password_reset_confirm', kwargs={
            'uidb64': urlsafe_base64_encode(force_bytes(user.pk)),
            'token': default_token_generator.make_token(user),
        })
        body = (
            f'Hi {greeting},\n\n'
            f'{organization.name} is approved to list with Listojo.\n\n'
            f'Set your password to finish setting up your account:\n'
            f'{site}{path}\n\n'
            f'That link expires in a few days. If it does, request a new one at '
            f'{site}{reverse("password_reset")}\n\n'
            f'Your username is {user.get_username()}\n\n'
            f'Once you are in, you can upload your inventory at '
            f'{site}{reverse("partner_upload")}\n\n'
            f'— Listojo'
        )
    else:
        body = (
            f'Hi {greeting},\n\n'
            f'{organization.name} is approved to list with Listojo, and your '
            f'existing account now has access.\n\n'
            f'Sign in at {site}{reverse("login")} with the username '
            f'{user.get_username()}, then upload your inventory at '
            f'{site}{reverse("partner_upload")}\n\n'
            f'— Listojo'
        )

    try:
        send_mail(
            subject=f'{organization.name} is approved to list with Listojo',
            message=body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
        )
        return True
    except Exception:
        # The account is already correct; only the notification failed. Staff
        # see this in the admin message and can re-run the action.
        logger.exception('partner invite email failed for %s', user)
        return False
