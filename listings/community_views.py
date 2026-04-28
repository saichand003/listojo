from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render

from .forms import CommunityForm, FloorPlanForm, ListingInquiryForm, UnitForm
from .models import Community, CommunityImage, FloorPlan, Unit
from .services.community_service import handle_tour_request
from .services.event_tracker import log_community_event


def community_detail(request, pk):
    community = get_object_or_404(
        Community.objects.select_related('owner').prefetch_related('images'),
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

    floor_plans = community.floor_plans.prefetch_related('units').all()
    return render(request, 'listings/community_detail.html', {
        'community': community,
        'floor_plans': floor_plans,
        'inquiry_form': inquiry_form,
    })


@login_required
def create_community(request):
    if request.method == 'POST':
        form = CommunityForm(request.POST)
        images = request.FILES.getlist('images')
        if form.is_valid():
            community = form.save(commit=False)
            community.owner = request.user
            community.save()
            for i, img in enumerate(images[:20]):
                CommunityImage.objects.create(community=community, image=img, order=i)
            messages.success(request, 'Community created. Now add your floor plans and units below.')
            return redirect('edit_community', pk=community.pk)
    else:
        form = CommunityForm()
    return render(request, 'listings/create_community.html', {
        'form': form,
        'max_images': 20,
    })


@login_required
def edit_community(request, pk):
    community = get_object_or_404(Community, pk=pk, owner=request.user)

    if request.method == 'POST' and 'save_community' in request.POST:
        form = CommunityForm(request.POST, instance=community)
        new_images = request.FILES.getlist('images')
        delete_ids = [int(x) for x in request.POST.getlist('delete_images') if x.isdigit()]
        if form.is_valid():
            form.save()
            if delete_ids:
                community.images.filter(pk__in=delete_ids).delete()
            next_order = community.images.count()
            for i, img in enumerate(new_images[:20]):
                CommunityImage.objects.create(community=community, image=img, order=next_order + i)
            messages.success(request, 'Community updated.')
            return redirect('edit_community', pk=community.pk)
    else:
        form = CommunityForm(instance=community)

    floor_plans = community.floor_plans.prefetch_related('units').all()
    return render(request, 'listings/edit_community.html', {
        'community': community,
        'form': form,
        'floor_plans': floor_plans,
        'fp_form': FloorPlanForm(),
        'unit_form': UnitForm(),
        'existing_images': community.images.all(),
    })


@login_required
def add_floor_plan(request, community_pk):
    community = get_object_or_404(Community, pk=community_pk, owner=request.user)
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
def delete_floor_plan(request, pk):
    fp = get_object_or_404(FloorPlan, pk=pk, community__owner=request.user)
    community_pk = fp.community.pk
    if request.method == 'POST':
        fp.delete()
    return redirect('edit_community', pk=community_pk)


@login_required
def add_unit(request, floor_plan_pk):
    fp = get_object_or_404(FloorPlan, pk=floor_plan_pk, community__owner=request.user)
    if request.method == 'POST':
        form = UnitForm(request.POST)
        if form.is_valid():
            unit = form.save(commit=False)
            unit.floor_plan = fp
            unit.save()
        else:
            messages.error(request, 'Unit could not be saved. Check the fields.')
    return redirect('edit_community', pk=fp.community.pk)


@login_required
def edit_unit(request, pk):
    unit = get_object_or_404(Unit, pk=pk, floor_plan__community__owner=request.user)
    if request.method == 'POST':
        form = UnitForm(request.POST, instance=unit)
        if form.is_valid():
            form.save()
    return redirect('edit_community', pk=unit.floor_plan.community.pk)


@login_required
def delete_unit(request, pk):
    unit = get_object_or_404(Unit, pk=pk, floor_plan__community__owner=request.user)
    community_pk = unit.floor_plan.community.pk
    if request.method == 'POST':
        unit.delete()
    return redirect('edit_community', pk=community_pk)


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
    return render(request, 'listings/my_communities.html', {'communities': communities})
