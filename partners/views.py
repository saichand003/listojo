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
from django.db.models import Count, Max, Q
from django.shortcuts import get_object_or_404, redirect, render

from listings.models import Community, Listing
from listings.services.partner_import import CsvAdapter, import_partner_inventory
from partners.forms import AssistedOnboardingForm, InventoryUploadForm
from partners.models import ImportRun, Membership, Organization


def partner_required(view_fn):
    """
    Access requires membership in an organization, not a staff flag.

    Superusers pass through so support can see what a partner sees.
    """
    @functools.wraps(view_fn)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')

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
    organization = request.organization

    communities = (Community.objects
                   .filter(managed_by=organization)
                   .annotate(unit_total=Count('floor_plans__units',
                                              filter=Q(floor_plans__units__status='available')))
                   .order_by('name'))
    standalone = (Listing.objects
                  .filter(organization=organization)
                  .exclude(status='closed')
                  .order_by('-created_at'))

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
        'last_run': last_run,
        'pending_deactivation': pending,
    })


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
            # Partner-supplied URLs are fetched only once rights are on record.
            fetch_photos=not dry_run and organization.communities.filter(
                media_rights_confirmed=True).exists(),
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
def import_history(request):
    return render(request, 'partners/history.html', {
        'organization': request.organization,
        'organizations': request.partner_orgs,
        'runs': request.organization.import_runs.all()[:50],
    })
