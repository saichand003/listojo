from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import connection
from django.db.utils import OperationalError
from django.db import models as django_models
from django.db.models import Case, Count, IntegerField, Q, Sum, Value, When
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from datetime import timedelta, date

from classifieds_project.services.notifications import send_listing_inquiry_email
from .forms import ListingForm, ListingInquiryForm, validate_uploaded_images
from .models import CityWaitlist, Favourite, GuidedSearchEvent, Listing, ListingImage
from listings.services.search import build_listing_search_context
from portal.services.routing import least_loaded_agent
from portal.services.lead_service import create_or_update_lead, parse_budget, parse_move_in


def _render_db_setup_page(request):
    return render(request, 'db_not_ready.html', status=503)


def _listings_table_ready():
    try:
        return Listing._meta.db_table in connection.introspection.table_names()
    except OperationalError:
        return False


def listing_list(request):
    if not _listings_table_ready():
        return _render_db_setup_page(request)
    context = build_listing_search_context(request)
    context['new_threshold'] = timezone.now() - timedelta(hours=48)

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return render(request, 'listings/_listings_grid.html', context)

    context['show_agent_cta'] = bool(request.session.get('gs_lead_id'))
    return render(request, 'listings/listing_list.html', context)


def guided_search(request):
    if request.method == 'POST':
        GuidedSearchEvent.objects.create(event_type=GuidedSearchEvent.COMPLETE)

        # Collect search params from POST
        category   = request.POST.get('category', '').strip()
        city       = request.POST.get('city', '').strip()
        bedrooms   = request.POST.get('bedrooms', '').strip()
        max_budget = request.POST.get('max_price', '').strip()
        amenities  = request.POST.get('tags', '').strip()
        available_by = request.POST.get('available_by', '').strip()

        beds_int = None
        if bedrooms:
            try:
                beds_int = int(bedrooms)
            except ValueError:
                pass

        lead = create_or_update_lead(
            name=request.user.get_full_name().strip() or request.user.username if request.user.is_authenticated else 'Guest',
            email=request.user.email if request.user.is_authenticated else '',
            source='guided_search',
            city=city,
            property_type=category,
            bedrooms=beds_int,
            max_budget=parse_budget(max_budget),
            amenities=amenities,
            move_in_date=parse_move_in(available_by),
        )

        # Store lead pk in session so listing list can show the CTA
        request.session['gs_lead_id'] = lead.pk

        # Build redirect to listing list preserving all search params
        from urllib.parse import urlencode
        qs_params = {}
        for key in ('category', 'city', 'bedrooms', 'min_price', 'max_price',
                    'tags', 'available_by', 'property_type', 'fmm'):
            val = request.POST.get(key, '').strip()
            if val:
                qs_params[key] = val
        qs_params.setdefault('fmm', '1')
        from django.urls import reverse
        return redirect(reverse('listing_list') + '?' + urlencode(qs_params))

    GuidedSearchEvent.objects.create(event_type=GuidedSearchEvent.START)
    mode = request.GET.get('mode', '').strip()  # 'rent' | 'buy' | ''
    return render(request, 'listings/guided_search.html', {
        'category_choices': Listing.CATEGORY_CHOICES,
        'gs_mode': mode,
    })


def listing_detail(request, pk):
    if not _listings_table_ready():
        return _render_db_setup_page(request)

    listing = get_object_or_404(Listing.objects.select_related('owner').prefetch_related('images'), pk=pk)

    # Increment view count (skip owner's own visits)
    if not request.user.is_authenticated or request.user != listing.owner:
        Listing.objects.filter(pk=pk).update(view_count=django_models.F('view_count') + 1)
        listing.view_count += 1

    if request.method == 'POST':
        inquiry_form = ListingInquiryForm(request.POST)
        if inquiry_form.is_valid():
            inquiry = inquiry_form.save(commit=False)
            inquiry.listing = listing
            inquiry.save()
            send_listing_inquiry_email(listing, inquiry)
            # Create a lead record and auto-assign to the least-loaded staff agent
            lead = create_or_update_lead(
                name=inquiry.name,
                email=inquiry.email,
                phone=inquiry.phone or '',
                source='inquiry',
                listing=listing,
                assigned_agent=least_loaded_agent(),
            )
            messages.success(request, 'Your inquiry was sent to the lister.')
            return redirect('listing_detail', pk=listing.pk)
    else:
        inquiry_form = ListingInquiryForm()

    return render(
        request,
        'listings/listing_detail.html',
        {'listing': listing, 'inquiry_form': inquiry_form},
    )


@login_required
def edit_listing(request, pk):
    if not _listings_table_ready():
        return _render_db_setup_page(request)

    listing = get_object_or_404(Listing, pk=pk, owner=request.user)

    if request.method == 'POST':
        form = ListingForm(request.POST, instance=listing)
        new_files = request.FILES.getlist('images')

        # Process deletions first so count is accurate
        delete_ids = [int(x) for x in request.POST.getlist('delete_images') if x.isdigit()]
        existing_count = listing.images.count() - len(delete_ids)

        image_errors = validate_uploaded_images(new_files, existing_count=max(existing_count, 0))

        if form.is_valid() and not image_errors:
            form.save()
            # Delete selected images
            if delete_ids:
                listing.images.filter(pk__in=delete_ids).delete()
            # Save new images
            next_order = listing.images.count()
            for i, f in enumerate(new_files):
                ListingImage.objects.create(listing=listing, image=f, order=next_order + i)
            messages.success(request, 'Listing updated successfully.')
            return redirect('listing_detail', pk=listing.pk)
    else:
        form = ListingForm(instance=listing)
        image_errors = []

    return render(request, 'listings/edit_listing.html', {
        'form': form,
        'listing': listing,
        'existing_images': listing.images.all(),
        'image_errors': image_errors,
        'max_images': 8,
    })


@login_required
def toggle_favourite(request, pk):
    if request.method == 'POST':
        listing = get_object_or_404(Listing, pk=pk)
        fav, created = Favourite.objects.get_or_create(user=request.user, listing=listing)
        if not created:
            fav.delete()
            is_fav = False
        else:
            is_fav = True
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'is_favourite': is_fav})
    return redirect(request.POST.get('next', 'listing_list'))


@login_required
def saved_listings(request):
    favourites = (
        Favourite.objects
        .filter(user=request.user)
        .select_related('listing', 'listing__owner')
        .prefetch_related('listing__images')
        .order_by('-created_at')
    )
    listings = [f.listing for f in favourites]
    fav_ids = {l.pk for l in listings}
    return render(request, 'listings/saved_listings.html', {
        'listings': listings,
        'fav_ids': fav_ids,
    })


@login_required
def create_listing(request):
    if not _listings_table_ready():
        return _render_db_setup_page(request)

    if request.method == 'POST':
        form = ListingForm(request.POST)
        new_files = request.FILES.getlist('images')
        image_errors = validate_uploaded_images(new_files)

        # ── City launch gate ──────────────────────────────────────────
        if settings.LAUNCH_ACTIVE:
            submitted_city = request.POST.get('city', '').strip().lower()
            if submitted_city and submitted_city not in settings.LAUNCH_CITIES:
                return render(request, 'listings/coming_soon.html', {
                    'city': request.POST.get('city', '').strip().title(),
                })

        if form.is_valid() and not image_errors:
            listing = form.save(commit=False)
            listing.owner = request.user
            listing.save()
            for i, f in enumerate(new_files):
                ListingImage.objects.create(listing=listing, image=f, order=i)
            return redirect('listing_detail', pk=listing.pk)
    else:
        form = ListingForm()
        image_errors = []

    return render(request, 'listings/create_listing.html', {
        'form': form,
        'image_errors': image_errors,
        'max_images': 8,
    })


def waitlist_signup(request):
    """Handle city waitlist form submission."""
    if request.method == 'POST':
        email = request.POST.get('email', '').strip()
        city  = request.POST.get('city', '').strip()
        state = request.POST.get('state', '').strip()
        if email and city:
            CityWaitlist.objects.get_or_create(
                email=email,
                city=city.lower(),
                defaults={'state': state},
            )
        return render(request, 'listings/coming_soon.html', {
            'city':    city.title(),
            'joined':  True,
            'email':   email,
        })
    return redirect('listing_list')


@login_required
def delete_listing(request, pk):
    listing = get_object_or_404(Listing, pk=pk, owner=request.user)
    if request.method == 'POST':
        listing.delete()
        return redirect('profile')
    return render(request, 'listings/confirm_delete.html', {'listing': listing})


@login_required
def listing_inquiries(request, pk):
    listing = get_object_or_404(Listing, pk=pk, owner=request.user)
    inquiries = listing.inquiries.order_by('-created_at')
    return render(request, 'listings/listing_inquiries.html', {
        'listing':   listing,
        'inquiries': inquiries,
    })
