from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import connection
from django.db.utils import OperationalError
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from datetime import timedelta

from .forms import ListingForm, ListingInquiryForm, validate_uploaded_images
from .models import Favourite, Listing, ListingImage


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

    q = request.GET.get('q', '').strip()
    category = request.GET.get('category', '').strip()
    city = request.GET.get('city', '').strip()
    sort = request.GET.get('sort', 'latest').strip()
    tag = request.GET.get('tag', '').strip()

    if q:
        terms = [t.strip() for t in q.split(',') if t.strip()]
        for term in terms:
            listings = listings.filter(
                Q(title__icontains=term) | Q(tags__icontains=term) | Q(description__icontains=term)
            )
    if category:
        listings = listings.filter(category=category)
    if city:
        listings = listings.filter(city__icontains=city)
    if tag:
        listings = listings.filter(tags__icontains=tag)

    if sort == 'price_low':
        listings = listings.order_by('price', '-featured', '-created_at')
    elif sort == 'price_high':
        listings = listings.order_by('-price', '-featured', '-created_at')
    else:
        listings = listings.order_by('-featured', '-created_at')

    category_counts = dict(
        Listing.objects.values_list('category').annotate(total=Count('id'))
    )

    # Build set of favourited listing IDs for the current user
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
        'filters': {'q': q, 'category': category, 'city': city, 'sort': sort, 'tag': tag},
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
