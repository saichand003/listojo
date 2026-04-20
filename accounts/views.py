from datetime import timedelta

from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Sum
from django.http import HttpResponseForbidden
from django.shortcuts import redirect, render
from django.utils import timezone

from .forms import RegistrationForm
from listings.models import Listing, ListingInquiry


def register(request):
    if request.method == 'POST':
        form = RegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect('listing_list')
    else:
        form = RegistrationForm()
    return render(request, 'accounts/register.html', {'form': form})


@login_required
def profile(request):
    return render(request, 'accounts/profile.html', {})


@login_required
def my_listings(request):
    listings = (
        Listing.objects
        .filter(owner=request.user)
        .annotate(
            inquiry_count=Count('inquiries', distinct=True),
            save_count=Count('favourited_by', distinct=True),
        )
        .order_by('-created_at')
    )
    active_count  = listings.filter(status='active').count()
    draft_count   = listings.filter(status='draft').count()
    total_views   = listings.aggregate(t=Sum('view_count'))['t'] or 0
    return render(request, 'accounts/my_listings.html', {
        'my_listings':  listings,
        'active_count': active_count,
        'draft_count':  draft_count,
        'total_views':  total_views,
    })


@login_required
def inquiries_overview(request):
    inquiries = (
        ListingInquiry.objects
        .filter(listing__owner=request.user)
        .select_related('listing')
        .order_by('-created_at')
    )
    unread_count = inquiries.filter(is_read=False).count() if hasattr(ListingInquiry, 'is_read') else 0
    return render(request, 'accounts/inquiries_overview.html', {
        'inquiries':    inquiries,
        'unread_count': unread_count,
    })


@login_required
def performance(request):
    listings = (
        Listing.objects
        .filter(owner=request.user, status='active')
        .annotate(
            inquiry_count=Count('inquiries', distinct=True),
            save_count=Count('favourited_by', distinct=True),
        )
        .order_by('-view_count')
    )
    totals = listings.aggregate(
        total_views=Sum('view_count'),
        total_inquiries=Count('inquiries', distinct=True),
        total_saves=Count('favourited_by', distinct=True),
    )
    return render(request, 'accounts/performance.html', {
        'listings': listings,
        'totals':   totals,
    })


@login_required
def agent_dashboard(request):
    if not request.user.is_staff:
        return HttpResponseForbidden()
    now = timezone.now()
    my_listings = (
        Listing.objects
        .filter(owner=request.user)
        .annotate(
            inquiry_count=Count('inquiries', distinct=True),
            save_count=Count('favourited_by', distinct=True),
        )
        .order_by('-created_at')
    )
    active_count  = my_listings.filter(status='active').count()
    pending_count = my_listings.filter(status='pending').count()
    recent_inquiries = (
        ListingInquiry.objects
        .filter(listing__owner=request.user)
        .select_related('listing')
        .order_by('-created_at')[:10]
    )
    new_inquiries_7 = ListingInquiry.objects.filter(
        listing__owner=request.user,
        created_at__gte=now - timedelta(days=7),
    ).count()
    return render(request, 'accounts/agent_dashboard.html', {
        'my_listings':      my_listings,
        'active_count':     active_count,
        'pending_count':    pending_count,
        'recent_inquiries': recent_inquiries,
        'new_inquiries_7':  new_inquiries_7,
    })
