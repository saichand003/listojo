from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import connection
from django.db.utils import OperationalError
from django.db.models import Case, Count, IntegerField, Q, Value, When
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from datetime import timedelta

from .forms import ListingForm, ListingInquiryForm, validate_uploaded_images
from .models import CityWaitlist, Favourite, Listing, ListingImage


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

    listings = Listing.objects.select_related('owner').prefetch_related('images').all()

    q         = request.GET.get('q', '').strip()
    category  = request.GET.get('category', '').strip()
    city      = request.GET.get('city', '').strip()
    sort      = request.GET.get('sort', 'latest').strip()
    tag       = request.GET.get('tag', '').strip()
    min_price      = request.GET.get('min_price', '').strip()
    max_price      = request.GET.get('max_price', '').strip()
    tags_raw       = request.GET.get('tags', '').strip()
    available_by   = request.GET.get('available_by', '').strip()

    # ── Text search ──
    terms = [t.strip() for t in q.split(',') if t.strip()] if q else []
    for term in terms:
        listings = listings.filter(
            Q(title__icontains=term) | Q(tags__icontains=term) | Q(description__icontains=term)
        )

    # ── Filters ──
    if category:
        listings = listings.filter(category=category)
    if city:
        listings = listings.filter(city__icontains=city)
    if tag:
        listings = listings.filter(tags__icontains=tag)

    # Quality tags (multi-select from chips)
    quality_tags = [t.strip() for t in tags_raw.split(',') if t.strip()]
    for qt in quality_tags:
        listings = listings.filter(tags__icontains=qt)

    # Price range
    try:
        if min_price:
            listings = listings.filter(price__gte=float(min_price))
        if max_price:
            listings = listings.filter(price__lte=float(max_price))
    except ValueError:
        pass

    # Availability — show listings available on or before the requested date
    # (listings with no available_from are treated as available now)
    if available_by:
        from datetime import date as _date
        try:
            _avail = _date.fromisoformat(available_by)
            listings = listings.filter(
                Q(available_from__isnull=True) | Q(available_from__lte=_avail)
            )
        except ValueError:
            pass

    # ── Relevance scoring (title match > tag match > description only) ──
    if terms:
        score_cases = []
        for term in terms:
            score_cases.append(When(title__icontains=term, then=Value(3)))
            score_cases.append(When(tags__icontains=term, then=Value(2)))
            score_cases.append(When(description__icontains=term, then=Value(1)))
        listings = listings.annotate(
            relevance=Case(*score_cases, default=Value(0), output_field=IntegerField())
        )

    # ── Ordering ──
    if sort == 'price_low':
        listings = listings.order_by('price', '-featured', '-created_at')
    elif sort == 'price_high':
        listings = listings.order_by('-price', '-featured', '-created_at')
    elif sort == 'best_match' and terms:
        listings = listings.order_by('-relevance', '-featured', '-created_at')
    else:
        listings = listings.order_by('-featured', '-created_at')

    # Auto-switch to best_match when user is searching and hasn't chosen another sort
    if terms and sort == 'latest':
        listings = listings.order_by('-relevance', '-featured', '-created_at')
        sort = 'best_match'

    category_counts = dict(
        Listing.objects.values_list('category').annotate(total=Count('id'))
    )

    fav_ids = set()
    if request.user.is_authenticated:
        fav_ids = set(Favourite.objects.filter(user=request.user).values_list('listing_id', flat=True))

    context = {
        'listings': list(listings),
        'fav_ids': fav_ids,
        'category_choices': Listing.CATEGORY_CHOICES,
        'category_counts': category_counts,
        'total_listings': Listing.objects.count(),
        'featured_count': Listing.objects.filter(featured=True).count(),
        'filters': {
            'q': q, 'category': category, 'city': city, 'sort': sort, 'tag': tag,
            'min_price': min_price, 'max_price': max_price, 'tags': tags_raw,
            'available_by': available_by,
        },
        'active_quality_tags': quality_tags,
        'new_threshold': timezone.now() - timedelta(hours=48),
    }

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return render(request, 'listings/_listings_grid.html', context)

    return render(request, 'listings/listing_list.html', context)


def listing_detail(request, pk):
    if not _listings_table_ready():
        return _render_db_setup_page(request)

    listing = get_object_or_404(Listing.objects.select_related('owner').prefetch_related('images'), pk=pk)

    if request.method == 'POST':
        inquiry_form = ListingInquiryForm(request.POST)
        if inquiry_form.is_valid():
            inquiry = inquiry_form.save(commit=False)
            inquiry.listing = listing
            inquiry.save()
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
