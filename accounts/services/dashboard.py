from __future__ import annotations

from datetime import timedelta

from django.db.models import Count, Q, Sum
from django.utils import timezone

from listings.models import Community, Listing, ListingInquiry
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
        'on_hold_count': listings.filter(status='on_hold').count(),
        'closed_count': listings.filter(status='closed').count(),
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
    communities = (
        Community.objects.filter(owner=user)
        .annotate(
            view_count=Count('events', filter=Q(events__event_type='click'), distinct=True),
            inquiry_count=Count('events', filter=Q(events__event_type='tour_request'), distinct=True),
            save_count=Count('leads', distinct=True),
        )
        .order_by('-view_count', '-created_at')
    )

    listing_totals = listings.aggregate(
        total_views=Sum('view_count'),
        total_inquiries=Count('inquiries', distinct=True),
        total_saves=Count('favourited_by', distinct=True),
    )
    community_totals = communities.aggregate(
        total_views=Sum('view_count'),
        total_inquiries=Sum('inquiry_count'),
        total_saves=Sum('save_count'),
    )
    totals = {
        'total_views': (listing_totals['total_views'] or 0) + (community_totals['total_views'] or 0),
        'total_inquiries': (listing_totals['total_inquiries'] or 0) + (community_totals['total_inquiries'] or 0),
        'total_saves': (listing_totals['total_saves'] or 0) + (community_totals['total_saves'] or 0),
    }

    items = [
        {
            'kind': 'listing',
            'pk': listing.pk,
            'title': listing.title,
            'city': listing.city,
            'price': listing.price,
            'price_unit': listing.price_unit,
            'view_count': listing.view_count,
            'inquiry_count': listing.inquiry_count,
            'save_count': listing.save_count,
            'url_name': 'listing_detail',
        }
        for listing in listings
    ]
    items.extend([
        {
            'kind': 'community',
            'pk': community.pk,
            'title': community.name,
            'city': community.city,
            'price': None,
            'price_unit': '',
            'view_count': community.view_count,
            'inquiry_count': community.inquiry_count,
            'save_count': community.save_count,
            'url_name': 'community_detail',
        }
        for community in communities
    ])
    items.sort(key=lambda item: item['view_count'], reverse=True)

    return {'items': items, 'totals': totals, 'has_inventory': bool(items)}


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
