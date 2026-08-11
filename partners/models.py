"""
Partner organizations and the management relationship to inventory.

The core idea: a building outlives both the person who typed it in and the
company that manages it. So three facts that `Listing.owner` used to collapse
are kept apart here —

    who manages it now    -> Community.managed_by / Listing.organization
    who may edit it       -> Membership
    whose feed record it is -> SourceRecordMap

Management changes hands. When it does, the Community keeps its identity, its
units, its lead history and its coordinates; only the assignment moves.
"""
from __future__ import annotations

from django.contrib.auth.models import User
from django.db import models
from django.utils import timezone


class Organization(models.Model):
    """A property-management company or apartment operator."""

    STATUS_CHOICES = [
        ('active',    'Active'),
        ('onboarding', 'Onboarding'),
        ('inactive',  'Inactive'),
    ]

    name = models.CharField(max_length=160)
    #: Short stable slug used on the CLI and in feed configuration ("acme").
    slug = models.SlugField(max_length=80, unique=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='onboarding')

    contact_name  = models.CharField(max_length=120, blank=True, default='')
    contact_email = models.EmailField(blank=True, default='')
    contact_phone = models.CharField(max_length=30, blank=True, default='')
    website       = models.URLField(blank=True, default='')

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name

    @property
    def owner_user(self) -> User | None:
        """The account inventory is attributed to when a feed creates rows."""
        membership = (self.memberships.filter(role='owner').order_by('pk').first()
                      or self.memberships.order_by('pk').first())
        return membership.user if membership else None

    def manages(self, community) -> bool:
        """True when this org currently holds the management assignment."""
        return self.assignments.filter(community=community, ended_at__isnull=True).exists()


class Membership(models.Model):
    """
    A person's access to an organization.

    Deleting the person deletes only this row. Their employer's portfolio is
    untouched, which is the entire point of the model.
    """

    ROLE_CHOICES = [
        ('owner',  'Owner'),
        ('member', 'Member'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='partner_memberships')
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE,
                                     related_name='memberships')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='member')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [('user', 'organization')]
        ordering = ['organization', 'role', 'pk']

    def __str__(self):
        return f'{self.user} @ {self.organization} ({self.role})'


class ManagementAssignment(models.Model):
    """
    Which organization managed a community, and when.

    Append-only. An open row (`ended_at` null) is the current manager; closing
    it and opening another is how a property changes hands. History cannot be
    reconstructed after the fact, which is why it is recorded from day one even
    though no property has switched yet.
    """

    community = models.ForeignKey('listings.Community', on_delete=models.CASCADE,
                                  related_name='management_assignments')
    organization = models.ForeignKey(Organization, on_delete=models.PROTECT,
                                     related_name='assignments')
    started_at = models.DateTimeField(default=timezone.now)
    ended_at   = models.DateTimeField(null=True, blank=True)
    note       = models.CharField(max_length=300, blank=True, default='')

    class Meta:
        ordering = ['-started_at']

    def __str__(self):
        window = f'{self.started_at:%Y-%m-%d} → ' + (
            f'{self.ended_at:%Y-%m-%d}' if self.ended_at else 'present')
        return f'{self.community} managed by {self.organization} ({window})'

    @property
    def is_current(self) -> bool:
        return self.ended_at is None


class SourceRecordMap(models.Model):
    """
    Blueprint §16's SOURCE_RECORD_MAP: one partner's ID for a community.

    A building has one identity in Listojo but a different ID in every partner's
    PMS. Without this table, a property changing managers imports as a second
    community, because the incoming feed carries an ID we have never seen.
    """

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE,
                                     related_name='source_records')
    #: The partner's own identifier for the property, straight from their feed.
    source_id = models.CharField(max_length=120, db_index=True)
    community = models.ForeignKey('listings.Community', on_delete=models.CASCADE,
                                  related_name='source_records')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [('organization', 'source_id')]
        ordering = ['organization', 'source_id']

    def __str__(self):
        return f'{self.organization}:{self.source_id} → {self.community}'


class PartnerApplication(models.Model):
    """
    A property manager asking to join Listojo, before any account exists.

    Deliberately not self-serve signup. A partner account can publish inventory
    and media, and blueprint §14 requires establishing that they are authorized
    to do so for those properties — which a signup form cannot verify. Staff
    review, create the Organization, and invite the contact.
    """

    STATUS_CHOICES = [
        ('new',       'New'),
        ('contacted', 'Contacted'),
        ('approved',  'Approved'),
        ('declined',  'Declined'),
    ]

    PORTFOLIO_CHOICES = [
        ('1-25',    '1–25 units'),
        ('26-100',  '26–100 units'),
        ('101-500', '101–500 units'),
        ('500+',    '500+ units'),
    ]

    company_name  = models.CharField(max_length=160)
    contact_name  = models.CharField(max_length=120)
    contact_email = models.EmailField()
    contact_phone = models.CharField(max_length=30, blank=True, default='')
    website       = models.URLField(blank=True, default='')

    portfolio_size = models.CharField(max_length=20, choices=PORTFOLIO_CHOICES, blank=True, default='')
    markets        = models.CharField(max_length=200, blank=True, default='',
                         help_text='Cities or submarkets, e.g. Dallas, Plano, Frisco')
    pms_name       = models.CharField(max_length=80, blank=True, default='',
                         help_text='RealPage, Yardi, Entrata, AppFolio, other, or unknown')
    notes          = models.TextField(blank=True, default='')

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='new')
    #: Set once staff turn this application into a real partner.
    organization = models.ForeignKey(Organization, null=True, blank=True,
                                     on_delete=models.SET_NULL, related_name='applications')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.company_name} ({self.status})'


class ImportRun(models.Model):
    """
    One inventory upload. Blueprint §16's FEED_RUNS, in its simplest form.

    Exists mainly so the portal can answer "when was this last refreshed?" —
    the question that tells a partner their listings are going stale, and tells
    Listojo which partners have quietly stopped sending.
    """

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE,
                                     related_name='import_runs')
    started_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name='partner_import_runs')
    source = models.CharField(max_length=40, default='portal_csv')
    filename = models.CharField(max_length=200, blank=True, default='')

    created_at = models.DateTimeField(auto_now_add=True)
    succeeded  = models.BooleanField(default=True)
    summary    = models.CharField(max_length=400, blank=True, default='')
    rejected_count = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        state = 'ok' if self.succeeded else 'failed'
        return f'{self.organization} {self.created_at:%Y-%m-%d %H:%M} ({state})'


class AssistedOnboardingRequest(models.Model):
    """
    Blueprint §21: "I don't know / help me connect".

    A partner who cannot answer "what is your feed URL" is a normal case, not an
    error. This captures the §19 discovery questions as a product feature rather
    than a phone call Listojo has to make.
    """

    STATUS_CHOICES = [
        ('new',         'New'),
        ('in_progress', 'In progress'),
        ('resolved',    'Resolved'),
    ]

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE,
                                     related_name='onboarding_requests')
    submitted_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL,
                                     related_name='partner_onboarding_requests')

    pms_name = models.CharField(max_length=80, blank=True, default='',
                   help_text='RealPage, Yardi, Entrata, AppFolio, other, or unknown')
    syndicates_elsewhere = models.BooleanField(default=False)
    syndication_targets  = models.CharField(max_length=300, blank=True, default='',
                               help_text='Zillow, Apartments.com, Zumper, …')
    syndication_vendor   = models.CharField(max_length=160, blank=True, default='')
    technical_contact_name  = models.CharField(max_length=120, blank=True, default='')
    technical_contact_email = models.EmailField(blank=True, default='')
    notes = models.TextField(blank=True, default='')

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='new')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'Assisted onboarding — {self.organization} ({self.status})'


def transfer_management(community, *, to_organization, note: str = '') -> ManagementAssignment:
    """
    Hand a community from its current manager to another organization.

    Closes any open assignment, opens a new one and repoints `managed_by`. The
    community, its floor plans, units and history are untouched — only who
    controls it changes.

    Media is deliberately NOT carried over as authorized: display rights came
    from the previous partner's agreement (blueprint §14), so the new manager
    re-grants them.
    """
    now = timezone.now()
    community.management_assignments.filter(ended_at__isnull=True).update(ended_at=now)

    assignment = ManagementAssignment.objects.create(
        community=community, organization=to_organization, started_at=now, note=note)

    community.managed_by = to_organization
    community.media_rights_confirmed = False
    community.save(update_fields=['managed_by', 'media_rights_confirmed'])

    return assignment
