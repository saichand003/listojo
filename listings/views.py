from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import connection
from django.db.utils import OperationalError
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect, render

from .forms import ListingForm, ListingInquiryForm
from .models import Listing


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

    listings = Listing.objects.select_related('owner').all()

    q = request.GET.get('q', '').strip()
    category = request.GET.get('category', '').strip()
    city = request.GET.get('city', '').strip()
    sort = request.GET.get('sort', 'latest').strip()

    if q:
        listings = listings.filter(title__icontains=q)
    if category:
        listings = listings.filter(category=category)
    if city:
        listings = listings.filter(city__icontains=city)

    if sort == 'price_low':
        listings = listings.order_by('price', '-featured', '-created_at')
    elif sort == 'price_high':
        listings = listings.order_by('-price', '-featured', '-created_at')

    category_counts = dict(
        Listing.objects.values_list('category').annotate(total=Count('id'))
    )

    context = {
        'listings': list(listings),
        'category_choices': Listing.CATEGORY_CHOICES,
        'category_counts': category_counts,
        'total_listings': Listing.objects.count(),
        'featured_count': Listing.objects.filter(featured=True).count(),
        'filters': {'q': q, 'category': category, 'city': city, 'sort': sort},
    }
    return render(request, 'listings/listing_list.html', context)


def listing_detail(request, pk):
    if not _listings_table_ready():
        return _render_db_setup_page(request)

    listing = get_object_or_404(Listing.objects.select_related('owner'), pk=pk)

    if request.method == 'POST':
        inquiry_form = ListingInquiryForm(request.POST)
        if inquiry_form.is_valid():
            inquiry = inquiry_form.save(commit=False)
            inquiry.listing = listing
            inquiry.save()
            messages.success(request, 'Your inquiry was sent to the poster.')
            return redirect('listing_detail', pk=listing.pk)
    else:
        inquiry_form = ListingInquiryForm()

    return render(
        request,
        'listings/listing_detail.html',
        {'listing': listing, 'inquiry_form': inquiry_form},
    )


@login_required
def create_listing(request):
    if not _listings_table_ready():
        return _render_db_setup_page(request)

    if request.method == 'POST':
        form = ListingForm(request.POST, request.FILES)
        if form.is_valid():
            listing = form.save(commit=False)
            listing.owner = request.user
            listing.save()
            return redirect('listing_detail', pk=listing.pk)
    else:
        form = ListingForm()
    return render(request, 'listings/create_listing.html', {'form': form})
