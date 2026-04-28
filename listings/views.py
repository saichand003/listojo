from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.db import connection
from django.db.utils import OperationalError
from django.db import models as django_models
from django.db.models import Case, Count, IntegerField, Q, Sum, Value, When
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_protect
from datetime import timedelta, date

from listojo.services.notifications import send_listing_inquiry_email
from .forms import ListingForm, ListingInquiryForm, validate_uploaded_images
from .models import CityWaitlist, Favourite, GuidedSearchEvent, Listing, ListingImage, ListingInquiry, SavedSearch
from listings.services.search import build_listing_search_context
from listings.services.valuation import predict_price
from listings.services.event_tracker import log_event, log_impression_batch
from portal.services.routing import least_loaded_agent
from portal.services.lead_service import create_or_update_lead, parse_budget, parse_move_in


def _render_db_setup_page(request):
    return render(request, 'db_not_ready.html', status=503)


def _listings_table_ready():
    try:
        return Listing._meta.db_table in connection.introspection.table_names()
    except OperationalError:
        return False


def home(request):
    if not _listings_table_ready():
        return _render_db_setup_page(request)
    trending_rentals = (
        Listing.objects.filter(category='rentals', status='active', parent__isnull=True)
        .select_related('owner').prefetch_related('images')
        .order_by('-view_count', '-created_at')[:5]
    )
    trending_properties = (
        Listing.objects.filter(category='properties', status='active', parent__isnull=True)
        .select_related('owner').prefetch_related('images')
        .order_by('-view_count', '-created_at')[:5]
    )
    cities = list(
        Listing.objects.filter(status='active', parent__isnull=True)
        .exclude(city='').values_list('city', flat=True)
        .distinct().order_by('city')[:12]
    )
    listing_count = Listing.objects.filter(status='active', parent__isnull=True).count()
    city_count = Listing.objects.filter(status='active', parent__isnull=True).exclude(city='').values('city').distinct().count()
    landlord_count = Listing.objects.filter(status='active', parent__isnull=True).values('owner').distinct().count()
    return render(request, 'listings/home.html', {
        'trending_rentals': trending_rentals,
        'trending_properties': trending_properties,
        'cities': cities,
        'stats': {
            'listing_count': listing_count,
            'city_count': city_count,
            'landlord_count': landlord_count,
        },
    })


def listing_list(request):
    if not _listings_table_ready():
        return _render_db_setup_page(request)
    import uuid
    context = build_listing_search_context(request)
    context['new_threshold'] = timezone.now() - timedelta(hours=48)
    context['search_id'] = str(uuid.uuid4())

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return render(request, 'listings/_listings_grid.html', context)

    context['show_agent_cta'] = bool(request.session.get('gs_lead_id'))

    # Resume banner: only on the first page load after a fresh login
    just_logged_in = request.session.pop('show_saved_search_banner', False)
    if request.user.is_authenticated and just_logged_in and not request.GET.get('fmm'):
        context['saved_searches'] = list(
            SavedSearch.objects.filter(user=request.user).order_by('search_type')
        )
    else:
        context['saved_searches'] = []

    return render(request, 'listings/listing_list.html', context)


def guided_search(request):
    if request.method == 'POST':
        GuidedSearchEvent.objects.create(event_type=GuidedSearchEvent.COMPLETE)

        # Collect search params from POST
        category      = request.POST.get('category', '').strip()
        city          = request.POST.get('city', '').strip()
        bedrooms      = request.POST.get('bedrooms', '').strip()
        max_budget    = request.POST.get('max_price', '').strip()
        amenities     = request.POST.get('tags', '').strip()
        available_by  = request.POST.get('available_by', '').strip()
        priority      = request.POST.get('priority', '').strip()
        urgency       = request.POST.get('urgency', '').strip()
        income_raw    = request.POST.get('monthly_income', '').strip()
        property_type = request.POST.get('property_type', '').strip()

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
            property_type=property_type or category,
            bedrooms=beds_int,
            max_budget=parse_budget(max_budget),
            amenities=amenities,
            move_in_date=parse_move_in(available_by),
            priority=priority,
            urgency=urgency,
            monthly_income=parse_budget(income_raw),
        )

        # Store lead pk in session so listing list can show the CTA
        request.session['gs_lead_id'] = lead.pk

        # Persist guided search so returning users can resume it
        if request.user.is_authenticated:
            search_type = 'buy' if category == 'properties' else 'rent'
            SavedSearch.objects.update_or_create(
                user=request.user,
                search_type=search_type,
                defaults={
                    'city': city,
                    'max_budget': parse_budget(max_budget),
                    'bedrooms': beds_int,
                    'property_type': property_type,
                    'accommodation_type': request.POST.get('accommodation_type', '').strip(),
                    'amenities': amenities,
                    'available_by': available_by,
                    'priority': priority,
                    'urgency': urgency,
                    'monthly_income': parse_budget(income_raw),
                },
            )

        # Build redirect to listing list preserving all search params
        from urllib.parse import urlencode
        qs_params = {}
        for key in ('category', 'city', 'bedrooms', 'min_price', 'max_price',
                    'tags', 'available_by', 'property_type', 'fmm', 'priority', 'urgency'):
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

    listing = get_object_or_404(
        Listing.objects.select_related('owner').prefetch_related('images', 'units__images'),
        pk=pk,
    )

    # Increment view count (skip owner's own visits)
    if not request.user.is_authenticated or request.user != listing.owner:
        Listing.objects.filter(pk=pk).update(view_count=django_models.F('view_count') + 1)
        listing.view_count += 1
        log_event(request, listing, 'click')

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
            log_event(request, listing, 'contact')
            messages.success(request, 'Your inquiry was sent to the lister.')
            return redirect('listing_detail', pk=listing.pk)
    else:
        inquiry_form = ListingInquiryForm()

    return render(
        request,
        'listings/listing_detail.html',
        {'listing': listing, 'inquiry_form': inquiry_form, 'render_as_community': False},
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
            log_event(request, listing, 'unsave')
        else:
            is_fav = True
            log_event(request, listing, 'save')
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
    inquiries.filter(is_read=False).update(is_read=True)
    return render(request, 'listings/listing_inquiries.html', {
        'listing':   listing,
        'inquiries': inquiries,
    })


@login_required
def inquiry_detail(request, inquiry_id):
    inquiry = get_object_or_404(
        ListingInquiry.objects.select_related('listing'),
        pk=inquiry_id,
        listing__owner=request.user,
    )
    if not inquiry.is_read:
        ListingInquiry.objects.filter(pk=inquiry.pk, is_read=False).update(is_read=True)
        inquiry.is_read = True
    return render(request, 'listings/inquiry_detail.html', {
        'inquiry': inquiry,
        'listing': inquiry.listing,
    })


def listing_estimate(request, pk):
    """Return a LightGBM price estimate for a listing as JSON."""
    listing = get_object_or_404(Listing, pk=pk)
    result  = predict_price(listing)
    if result is None:
        return JsonResponse({'error': 'model_not_ready'}, status=404)
    return JsonResponse(result)


def listing_estimate_range(request):
    """Return a comparable price range for a not-yet-saved listing (used on create form)."""
    import types
    fl = types.SimpleNamespace(
        square_footage=request.GET.get('square_footage') or None,
        bedrooms=request.GET.get('bedrooms') or None,
        year_built=None,
        hoa_fee=None,
        bills_included=False,
        zip_code=request.GET.get('zip_code', ''),
        city=request.GET.get('city', ''),
        property_type=request.GET.get('property_type', ''),
        category=request.GET.get('category', ''),
        accommodation_type='',
        price_unit=request.GET.get('price_unit', 'mo'),
    )
    result = predict_price(fl)
    if result is None:
        return JsonResponse({'error': 'model_not_ready'}, status=404)
    return JsonResponse(result)

@csrf_protect
def log_impressions(request):
    """
    Batch impression endpoint called by the listing-list JS.
    Body: {search_id: str, impressions: [{pk, rank, fmm_score}, ...]}
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'method not allowed'}, status=405)
    rate_key = f'listing-impressions:{request.session.session_key or request.META.get("REMOTE_ADDR", "")}'
    hits = cache.get(rate_key, 0)
    if hits >= 120:
        return JsonResponse({'error': 'rate limited'}, status=429)
    import json
    from uuid import UUID
    try:
        data      = json.loads(request.body)
        sid_str   = data.get('search_id', '')
        search_id = UUID(sid_str) if sid_str else None
        items     = data.get('impressions', [])[:60]
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'ok': False}, status=400)
    cache.set(rate_key, hits + 1, 60)
    logged = log_impression_batch(request, items, search_id=search_id)
    return JsonResponse({'ok': True, 'logged': logged})
