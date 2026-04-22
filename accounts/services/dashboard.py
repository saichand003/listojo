from __future__ import annotations

from datetime import timedelta

from django.db.models import Count, Sum
from django.utils import timezone

from listings.models import Listing, ListingInquiry
from listings.services.visibility import active_listings


def owner_listing_overview(user) -> dict:
    listings = (
        Listing.objects.filter(owner=user)
        .annotate(
            inquiry_count=Count('inquiries', distinct=True),
            save_count=Count('favourited_by', distinct=True),
        )
        .order_by('-created_at')
    )
    return {
        'my_listings': listings,
        'active_count': listings.filter(status='active').count(),
        'draft_count': listings.filter(status='draft').count(),
        'total_views': listings.aggregate(t=Sum('view_count'))['t'] or 0,
    }


def owner_performance(user) -> dict:
    listings = (
        active_listings(Listing.objects.filter(owner=user))
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
    return {'listings': listings, 'totals': totals}


def owner_inquiries(user):
    return (
        ListingInquiry.objects.filter(listing__owner=user)
        .select_related('listing')
        .order_by('-created_at')
    )


def staff_agent_dashboard(user) -> dict:
    now = timezone.now()
    my_listings = (
        Listing.objects.filter(owner=user)
        .annotate(
            inquiry_count=Count('inquiries', distinct=True),
            save_count=Count('favourited_by', distinct=True),
        )
        .order_by('-created_at')
    )
    recent_inquiries = owner_inquiries(user)[:10]
    return {
        'my_listings': my_listings,
        'active_count': my_listings.filter(status='active').count(),
        'pending_count': my_listings.filter(status='pending').count(),
        'recent_inquiries': recent_inquiries,
        'new_inquiries_7': ListingInquiry.objects.filter(
            listing__owner=user,
            created_at__gte=now - timedelta(days=7),
        ).count(),
    }
