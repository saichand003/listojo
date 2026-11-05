from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from partners.models import Organization

from .forms import (
    MAX_COMMUNITY_PHOTOS,
    CommunityForm,
    FloorPlanForm,
    ListingInquiryForm,
    UnitForm,
    validate_uploaded_images,
)
from .models import Community, CommunityImage, FloorPlan, Unit
from .services.availability_checks import GRACE_PERIOD, community_for_token
from .services.community_photos import COMMUNITY, belongs_to_options, resolve_heading
from .services.community_service import handle_tour_request
from .services.event_tracker import log_community_event
from .services.match_prefs import resolve_match_prefs
from .services.ownership import editable_communities
from .views import _detail_match


def community_detail(request, pk):
    community = get_object_or_404(
        Community.objects
        .select_related('owner', 'nearest_downtown')
        # The proximity cards read these as bare `.all()` so a prefetch is
        # reused — see ProximityDisplayMixin.
        .prefetch_related('images', 'floor_plans__units', 'nearby_groceries__store',
                          'nearby_transit__station__agency'),
        pk=pk, status='active',
    )

    inquiry_form = ListingInquiryForm(request.POST or None)
    if request.method == 'POST':
        if inquiry_form.is_valid():
            inquiry = dict(inquiry_form.cleaned_data)
            inquiry['tour_type'] = request.POST.get('tour_type', '')
            success, error = handle_tour_request(request, community, inquiry)
            if success:
                messages.success(request, 'Your tour request was sent to the community.')
                return redirect('community_detail', pk=community.pk)
            messages.error(request, error)
        else:
            messages.error(request, 'Please check the form fields and try again.')
    elif not request.user.is_authenticated or request.user != community.owner:
        log_community_event(request, community, 'click')

    # The prefetched plans, so each card's units and photos come from memory.
    floor_plans = list(community.floor_plans.all())
    photo_groups = community.photo_groups
    for fp in floor_plans:
        # A unit inherits its plan's photos; the card shows them, opening the
        # shared viewer at the right index.
        fp.photo_tiles = [
            {'url': photo.image.url, 'index': group.start + n, 'heading': group.heading}
            for group in photo_groups if group.floor_plan is fp
            for n, photo in enumerate(group.photos)
        ]
    return render(request, 'listings/community_detail.html', {
        'community': community,
        'floor_plans': floor_plans,
        'photo_groups': photo_groups,
        'plan_specs': _plan_specs(floor_plans),
        'inquiry_form': inquiry_form,
        'match': _detail_match(request, community),
        'match_prefs': resolve_match_prefs(request),
    })


def _plan_specs(floor_plans):
    """
    The spec strip for a community: bedroom, bathroom and size ranges across
    its floor plans. A community has no single bed/bath count, so each tile
    shows the span ("1–3") instead, or the one value when every plan agrees.
    """
    plans = list(floor_plans)
    if not plans:
        return None

    def span(values, fmt=str):
        values = sorted(v for v in values if v is not None)
        if not values:
            return None
        lo, hi = fmt(values[0]), fmt(values[-1])
        return lo if lo == hi else f'{lo}–{hi}'

    def beds(n):
        return 'Studio' if n == 0 else str(n)

    def baths(n):
        return f'{float(n):g}'

    return {
        'bedrooms': span([p.bedrooms for p in plans], beds),
        'bathrooms': span([p.bathrooms for p in plans], baths),
        'sqft': span([p.square_footage for p in plans], lambda n: f'{n:,}'),
        'plan_count': len(plans),
    }


def _save_new_photos(request, community) -> list[str]:
    """
    Store the photos in `request.FILES['images']`, each with its heading.

    The upload widget posts one `new_belongs` / `new_shows` / `new_label` per
    file, in file order, so the lists line up. Returns validation errors; on
    any error nothing is saved, so the owner can fix the batch and resend it.
    """
    files = request.FILES.getlist('images')
    if not files:
        return []
    errors = validate_uploaded_images(files, existing_count=community.images.count(),
                                      max_count=MAX_COMMUNITY_PHOTOS, noun='community')
    if errors:
        return errors

    belongs = request.POST.getlist('new_belongs')
    shows = request.POST.getlist('new_shows')
    labels = request.POST.getlist('new_label')
    next_order = community.images.count()
    for n, upload in enumerate(files):
        floor_plan, tag, label = resolve_heading(
            community,
            belongs[n] if n < len(belongs) else COMMUNITY,
            shows[n] if n < len(shows) else '',
            labels[n] if n < len(labels) else '',
        )
        CommunityImage.objects.create(community=community, image=upload, order=next_order + n,
                                      floor_plan=floor_plan, shows=tag, custom_label=label)
    return []


def _edit_url(community_pk, anchor):
    """The edit page scrolled back to what was just changed."""
    return f"{reverse('edit_community', args=[community_pk])}#{anchor}"


def _editable_communities(user):
    """Owned outright, or run by a partner org the user belongs to."""
    return editable_communities(user, Community.objects.all())


def _csv_upload_url(user):
    """
    The side door for big portfolios: partner members get the CSV upload,
    everyone else the application that leads to it.
    """
    is_partner = Organization.objects.filter(memberships__user=user).exists()
    return reverse('partner_upload' if is_partner else 'partner_apply')


@login_required
def create_community(request):
    photo_errors = []
    if request.method == 'POST':
        form = CommunityForm(request.POST)
        files = request.FILES.getlist('images')
        photo_errors = validate_uploaded_images(files, max_count=MAX_COMMUNITY_PHOTOS,
                                                noun='community')
        if form.is_valid() and not photo_errors:
            community = form.save(commit=False)
            community.owner = request.user
            community.save()
            _save_new_photos(request, community)
            messages.success(request, 'Community created. Now add your floor plans, units '
                                      'and their photos below.')
            return redirect('edit_community', pk=community.pk)
    else:
        form = CommunityForm()
    return render(request, 'listings/create_community.html', {
        'form': form,
        'max_images': MAX_COMMUNITY_PHOTOS,
        'photo_errors': photo_errors,
        'community_shows': CommunityImage.COMMUNITY_SHOWS,
        'csv_upload_url': _csv_upload_url(request.user),
    })


@login_required
def edit_community(request, pk):
    community = get_object_or_404(_editable_communities(request.user), pk=pk)

    if request.method == 'POST' and 'save_community' in request.POST:
        form = CommunityForm(request.POST, instance=community)
        if form.is_valid():
            form.save()
            messages.success(request, 'Community updated.')
            return redirect('edit_community', pk=community.pk)
    else:
        form = CommunityForm(instance=community)

    floor_plans = list(community.floor_plans.prefetch_related('units'))
    return render(request, 'listings/edit_community.html', {
        'community': community,
        'form': form,
        'floor_plans': floor_plans,
        'fp_form': FloorPlanForm(),
        'unit_form': UnitForm(),
        'unit_statuses': Unit.STATUS_CHOICES,
        'visible_days_ahead': Unit.VISIBLE_DAYS_AHEAD,
        'existing_images': community.images.all(),
        'belongs_options': belongs_to_options(floor_plans),
        'community_shows': CommunityImage.COMMUNITY_SHOWS,
        'room_shows': CommunityImage.ROOM_SHOWS,
        'max_images': MAX_COMMUNITY_PHOTOS,
        'csv_upload_url': _csv_upload_url(request.user),
        'confirm_deadline': (community.confirmation_requested_at + GRACE_PERIOD
                             if community.confirmation_requested_at else None),
    })


@login_required
@require_POST
def save_community_photos(request, pk):
    """
    The photo manager on the edit page: re-heading and deleting existing
    photos, and uploading new ones, in one submit.
    """
    community = get_object_or_404(_editable_communities(request.user), pk=pk)

    delete_ids = {int(x) for x in request.POST.getlist('delete_images') if x.isdigit()}
    for photo in community.images.all():
        if photo.pk in delete_ids:
            photo.image.delete(save=False)
            photo.delete()
            continue
        key = str(photo.pk)
        if f'belongs_{key}' not in request.POST:
            continue
        floor_plan, tag, label = resolve_heading(
            community, request.POST[f'belongs_{key}'],
            request.POST.get(f'shows_{key}', ''), request.POST.get(f'label_{key}', ''))
        if (floor_plan, tag, label) != (photo.floor_plan, photo.shows, photo.custom_label):
            photo.floor_plan, photo.shows, photo.custom_label = floor_plan, tag, label
            photo.save(update_fields=['floor_plan', 'shows', 'custom_label'])

    errors = _save_new_photos(request, community)
    for error in errors:
        messages.error(request, error)
    if not errors:
        messages.success(request, 'Photos saved.')
    return redirect(_edit_url(community.pk, 'photos'))


@login_required
def add_floor_plan(request, community_pk):
    community = get_object_or_404(_editable_communities(request.user), pk=community_pk)
    if request.method == 'POST':
        form = FloorPlanForm(request.POST, request.FILES)
        if form.is_valid():
            fp = form.save(commit=False)
            fp.community = community
            fp.save()
        else:
            messages.error(request, 'Floor plan could not be saved. Check the fields.')
    return redirect('edit_community', pk=community.pk)


@login_required
@require_POST
def duplicate_floor_plan(request, pk):
    """
    Copy a plan's specs — for a landlord with several near-identical layouts.
    Units and photos stay with the original: unit numbers are unique, and the
    owner tags the new plan's own photos.
    """
    fp = get_object_or_404(FloorPlan, pk=pk, community__in=_editable_communities(request.user))
    copy = FloorPlan.objects.create(
        community=fp.community, name=f'{fp.name} (copy)'[:80], bedrooms=fp.bedrooms,
        bathrooms=fp.bathrooms, square_footage=fp.square_footage,
        floor_plan_image=fp.floor_plan_image.name or None, description=fp.description)
    messages.success(request, f'Duplicated "{fp.name}". Rename it and add its units below.')
    return redirect(_edit_url(fp.community_id, f'fp-{copy.pk}'))


@login_required
def delete_floor_plan(request, pk):
    fp = get_object_or_404(FloorPlan, pk=pk, community__in=_editable_communities(request.user))
    community_pk = fp.community.pk
    if request.method == 'POST':
        fp.delete()
    return redirect('edit_community', pk=community_pk)


@login_required
def add_unit(request, floor_plan_pk):
    fp = get_object_or_404(FloorPlan, pk=floor_plan_pk, community__in=_editable_communities(request.user))
    if request.method == 'POST':
        form = UnitForm(request.POST)
        if form.is_valid():
            unit = form.save(commit=False)
            unit.floor_plan = fp
            unit.save()
            fp.community.confirm_availability()
        else:
            messages.error(request, 'Unit could not be saved. Check the fields.')
    return redirect(_edit_url(fp.community_id, f'fp-{fp.pk}'))


@login_required
def edit_unit(request, pk):
    unit = get_object_or_404(Unit, pk=pk, floor_plan__community__in=_editable_communities(request.user))
    if request.method == 'POST':
        form = UnitForm(request.POST, instance=unit)
        if form.is_valid():
            form.save()
            unit.floor_plan.community.confirm_availability()
        else:
            messages.error(request, 'Unit could not be saved. Check the fields.')
    return redirect(_edit_url(unit.floor_plan.community_id, f'fp-{unit.floor_plan_id}'))


@login_required
def delete_unit(request, pk):
    unit = get_object_or_404(Unit, pk=pk, floor_plan__community__in=_editable_communities(request.user))
    community_pk = unit.floor_plan.community.pk
    if request.method == 'POST':
        unit.delete()
        unit.floor_plan.community.confirm_availability()
    return redirect('edit_community', pk=community_pk)


@login_required
@require_POST
def confirm_community_availability(request, pk):
    """The edit page's "Still accurate" button."""
    community = get_object_or_404(_editable_communities(request.user), pk=pk)
    community.confirm_availability()
    messages.success(request, f'Availability confirmed for {community.name}. '
                              f'We will check again in 14 days.')
    # The partner portal's attention queue posts here too; send it back there.
    next_url = request.POST.get('next', '')
    if next_url and url_has_allowed_host_and_scheme(
            next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        return redirect(next_url)
    return redirect('edit_community', pk=community.pk)


def confirm_availability_link(request, token):
    """
    The one-click link in the "still available?" email. Signed, so it works
    signed out. GET only shows the button — mail scanners prefetch links, and
    one must not confirm a listing on the owner's behalf.
    """
    community = community_for_token(token)
    if community is None:
        return render(request, 'listings/confirm_availability.html',
                      {'invalid': True}, status=404)
    if request.method == 'POST':
        community.confirm_availability()
        return render(request, 'listings/confirm_availability.html',
                      {'community': community, 'confirmed': True})
    return render(request, 'listings/confirm_availability.html', {
        'community': community,
        'units': Unit.objects.filter(floor_plan__community=community)
                 .exclude(status__in=(Unit.LEASED, Unit.OFF_MARKET))
                 .select_related('floor_plan').order_by('floor_plan__bedrooms', 'unit_number'),
    })


@login_required
def my_communities(request):
    communities = (
        Community.objects
        .filter(owner=request.user)
        .annotate(
            lead_count=Count('leads', distinct=True),
            impression_count=Count('events', filter=Q(events__event_type='impression'), distinct=True),
            tour_request_count=Count('events', filter=Q(events__event_type='tour_request'), distinct=True),
        )
        .prefetch_related('images', 'floor_plans__units')
    )
    return render(request, 'listings/my_communities.html', {
        'communities': communities,
        'csv_upload_url': _csv_upload_url(request.user),
    })
