"""
Listojo Partners — the property manager's own surface.

Deliberately thin. A PM can see their portfolio, tell whether it is stale, push
a new CSV, and ask for help connecting. Everything else (feed health dashboards,
role matrices, automated scheduling) waits until a partner asks for it.
"""
from __future__ import annotations

import functools
import io

from django.contrib import messages
from django.contrib.auth.views import redirect_to_login
from django.db.models import Count, Max, Min, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from listings.models import Community, Listing
from listings.services.availability_checks import GRACE_PERIOD
from listings.services.partner_import import CsvAdapter, import_partner_inventory
from partners.forms import (
    AssistedOnboardingForm,
    InventoryUploadForm,
    PartnerApplicationForm,
)
from partners.models import ImportRun, Membership, Organization


def partner_required(view_fn):
    """
    Access requires membership in an organization, not a staff flag.

    Superusers pass through so support can see what a partner sees.
    """
    @functools.wraps(view_fn)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            # Carry the destination through the login round-trip. A bare
            # redirect('login') drops it, and the partner lands on the renter
            # home after signing in — the one page they did not ask for.
            return redirect_to_login(request.get_full_path())

        organizations = list(Organization.objects.filter(
            memberships__user=request.user).distinct())
        if not organizations and request.user.is_superuser:
            organizations = list(Organization.objects.all())
        if not organizations:
            return render(request, 'partners/no_access.html', status=403)

        request.partner_orgs = organizations
        request.organization = _selected_org(request, organizations)
        return view_fn(request, *args, **kwargs)
    return wrapper


def _selected_org(request, organizations):
    """Support people belonging to more than one org via ?org=<slug>."""
    slug = request.GET.get('org') or request.session.get('partner_org_slug')
    for organization in organizations:
        if organization.slug == slug:
            request.session['partner_org_slug'] = slug
            return organization
    return organizations[0]


@partner_required
def dashboard(request):
    """
    The property list — the page a PM opens every morning. Each row carries
    what a leasing manager scans for (live or not, vacancy, rent, photos,
    availability freshness), and anything blocking a listing is pulled up
    into one "Needs attention" queue so nobody has to read the whole table.
    """
    organization = request.organization

    communities = list(
        Community.objects
        .filter(managed_by=organization)
        .annotate(
            unit_total=Count('floor_plans__units',
                             filter=Q(floor_plans__units__status='available'), distinct=True),
            units_all=Count('floor_plans__units', distinct=True),
            photo_total=Count('images', distinct=True),
            rent_min=Min('floor_plans__units__price',
                         filter=Q(floor_plans__units__status='available')),
            rent_max=Max('floor_plans__units__price',
                         filter=Q(floor_plans__units__status='available')),
        )
        .select_related('media_rights_confirmed_by')
        .prefetch_related('images')
        .order_by('name')
    )
    standalone = (Listing.objects
                  .filter(organization=organization)
                  .exclude(status='closed')
                  .order_by('-created_at'))

    attention = []
    for c in communities:
        c.thumb = next(iter(c.images.all()), None)
        c.issues = _community_issues(c)
        if c.status != 'active' or c.availability_hidden_at:
            c.health = 'hidden'
        elif c.issues:
            c.health = 'attention'
        else:
            c.health = 'live'
        if c.issues:
            attention.append(c)

    last_run = organization.import_runs.first()
    pending = (Listing.objects.filter(organization=organization,
                                      deactivation_pending_since__isnull=False)
               .exclude(status='closed').count())

    return render(request, 'partners/dashboard.html', {
        'organization': organization,
        'organizations': request.partner_orgs,
        'communities': communities,
        'standalone': standalone,
        'unit_total': sum(c.unit_total for c in communities),
        'live_count': sum(1 for c in communities if c.health != 'hidden'),
        'attention': attention,
        'attention_items': sum(len(c.issues) for c in attention),
        'last_run': last_run,
        'pending_deactivation': pending,
        'upload_form': InventoryUploadForm(),
    })


def _community_issues(c):
    """
    What is stopping this property from listing well, most urgent first.
    Each issue is (kind, text, action) — the template turns `kind` into the
    right button, so the copy and the fix stay side by side.
    """
    issues = []
    if c.availability_hidden_at:
        issues.append(('hidden', 'Units hidden from renters — availability not confirmed', 'confirm'))
    elif c.confirmation_requested_at:
        due = c.confirmation_requested_at + GRACE_PERIOD
        issues.append(('due', f'Confirm availability by {due:%b} {due.day}', 'confirm'))
    if not c.media_rights_confirmed:
        issues.append(('rights', 'Media rights not confirmed — photos stay unpublished', 'rights'))
    if not c.photo_total:
        issues.append(('photos', 'No photos — listings with photos get far more tours', 'photos'))
    if not c.unit_total:
        issues.append(('vacancy', 'No available units — property is not shown in search', 'manage'))
    return issues


@partner_required
def upload_inventory(request):
    organization = request.organization
    form = InventoryUploadForm(request.POST or None, request.FILES or None)
    result = None

    if request.method == 'POST' and form.is_valid():
        upload = form.cleaned_data['csv_file']
        text = io.StringIO(upload.read().decode('utf-8-sig', errors='replace'))
        dry_run = 'preview' in request.POST

        result = import_partner_inventory(
            CsvAdapter(text),
            organization=organization,
            dry_run=dry_run,
        )

        if not dry_run:
            ImportRun.objects.create(
                organization=organization, started_by=request.user,
                filename=upload.name, succeeded=result.ok,
                summary=result.summary(), rejected_count=len(result.rejections))

            if result.ok and not result.rejections:
                messages.success(request, f'Inventory updated — {result.summary()}')
                return redirect('partner_dashboard')
            if result.ok:
                # Stay put so the partner can see which rows failed. Redirecting
                # would drop the only copy of that list.
                messages.success(request, f'Inventory updated — {result.summary()}')
            else:
                messages.error(request, result.aborted_reason)

    return render(request, 'partners/upload.html', {
        'organization': organization,
        'organizations': request.partner_orgs,
        'form': form,
        'result': result,
        'was_preview': 'preview' in request.POST,
        'runs': organization.import_runs.select_related('started_by')[:50],
    })


@partner_required
def assisted_onboarding(request):
    organization = request.organization
    form = AssistedOnboardingForm(request.POST or None)

    if request.method == 'POST' and form.is_valid():
        case = form.save(commit=False)
        case.organization = organization
        case.submitted_by = request.user
        case.save()
        messages.success(request, "Thanks — we'll be in touch to get your listings connected.")
        return redirect('partner_dashboard')

    return render(request, 'partners/onboarding.html', {
        'organization': organization,
        'organizations': request.partner_orgs,
        'form': form,
        'open_cases': organization.onboarding_requests.exclude(status='resolved'),
    })


@partner_required
@require_POST
def confirm_media_rights(request, pk):
    """
    The partner attests that they may publish a community's photos.

    Blueprint §14 rights are the partner's claim about their own media, so the
    partner makes it — staff ticking a box on their behalf records the wrong
    party. Scoped to the caller's own organization: `managed_by` in the lookup
    is the authorization check, not a filter.
    """
    community = get_object_or_404(Community, pk=pk,
                                  managed_by=request.organization)

    if community.media_rights_confirmed:
        return redirect('partner_dashboard')

    community.media_rights_confirmed = True
    community.media_rights_confirmed_by = request.user
    community.media_rights_confirmed_at = timezone.now()
    community.save(update_fields=['media_rights_confirmed',
                                  'media_rights_confirmed_by',
                                  'media_rights_confirmed_at'])

    messages.success(request, f'Media rights confirmed for {community.name}. '
                              f'Photos in your next upload will be published.')
    return redirect('partner_dashboard')


@partner_required
def import_history(request):
    """Upload and history are one "Imports" page; the old URL still works."""
    return upload_inventory.__wrapped__(request)


def apply_to_partner(request):
    """
    Public application — no login, no account created.

    Staff review it, create the Organization, and invite the contact. See
    PartnerApplication for why this is not self-serve signup.
    """
    form = PartnerApplicationForm(request.POST or None)
    submitted = False

    if request.method == 'POST' and form.is_valid():
        form.save()
        submitted = True
        form = PartnerApplicationForm()

    return render(request, 'partners/apply.html', {'form': form, 'submitted': submitted})
