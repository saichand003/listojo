from __future__ import annotations

from datetime import timedelta

from django.contrib.auth.models import User
from django.db.models import Count, Q, Sum
from django.utils import timezone

from chatapp.models import ChatMessage
from listings.models import GuidedSearchEvent, Listing, ListingInquiry
from listings.services.visibility import active_listings


def build_admin_dashboard_context() -> dict:
    now = timezone.now()
    last_7 = now - timedelta(days=7)
    last_30 = now - timedelta(days=30)

    total_users = User.objects.count()
    new_users_7 = User.objects.filter(date_joined__gte=last_7).count()
    new_users_30 = User.objects.filter(date_joined__gte=last_30).count()
    recent_users = User.objects.order_by('-date_joined')[:6]

    visible_qs = active_listings()
    total_listings = Listing.objects.count()
    active_count = visible_qs.count()
    new_listings_7 = Listing.objects.filter(created_at__gte=last_7).count()
    pending_count = Listing.objects.filter(status='pending').count()
    flagged_count = Listing.objects.filter(status='flagged').count()
    featured = Listing.objects.filter(featured=True).count()
    total_views = Listing.objects.aggregate(t=Sum('view_count'))['t'] or 0

    total_messages = ChatMessage.objects.count()
    total_inquiries = ListingInquiry.objects.count()
    new_inquiries_7 = ListingInquiry.objects.filter(created_at__gte=last_7).count()
    active_listers = User.objects.filter(listings__status='active').distinct().count()

    guided_starts = GuidedSearchEvent.objects.filter(event_type=GuidedSearchEvent.START).count()
    guided_completes = GuidedSearchEvent.objects.filter(event_type=GuidedSearchEvent.COMPLETE).count()
    contacted_listers = ListingInquiry.objects.values('email').distinct().count()
    chat_conversations = ChatMessage.objects.values('listing').distinct().count()

    funnel_steps = [
        {'label': 'Visitors', 'count': total_views},
        {'label': 'Started guided search', 'count': guided_starts},
        {'label': 'Completed intake', 'count': guided_completes},
        {'label': 'Contacted a lister', 'count': contacted_listers},
        {'label': 'Connected to agent', 'count': chat_conversations},
    ]
    funnel_max = funnel_steps[0]['count'] or 1
    for step in funnel_steps:
        step['pct'] = round(step['count'] / funnel_max * 100) if funnel_max else 0

    total_active = active_count or 1
    cat_map = dict(Listing.CATEGORY_CHOICES)
    cat_icons = {
        'roommates': '🤝', 'rentals': '🏠', 'properties': '🏡',
        'local_services': '🔧', 'jobs': '💼', 'buy_sell': '🛍️', 'events': '🎉',
    }

    rentals_with_beds = visible_qs.filter(category='rentals', bedrooms__isnull=False).count()
    rental_rows = []
    if rentals_with_beds:
        for beds, label in [(2, 'Rentals — 2 bed'), (1, 'Rentals — 1 bed'), (3, 'Rentals — 3+ bed')]:
            row_qs = visible_qs.filter(category='rentals', bedrooms__gte=3) if beds == 3 else visible_qs.filter(category='rentals', bedrooms=beds)
            count = row_qs.count()
            if count:
                rental_rows.append({'label': label, 'count': count, 'pct': round(count / total_active * 100), 'icon': '🏠'})
        studio_count = visible_qs.filter(category='rentals').filter(Q(property_type='studio') | Q(bedrooms=0)).count()
        if studio_count:
            rental_rows.append({'label': 'Studios', 'count': studio_count, 'pct': round(studio_count / total_active * 100), 'icon': '🏢'})
        exclude_rentals = True
    else:
        exclude_rentals = False

    category_rows = visible_qs.values('category').annotate(total=Count('id')).order_by('-total')
    if exclude_rentals:
        category_rows = category_rows.exclude(category='rentals')
    other_rows = [{
        'label': cat_map.get(row['category'], row['category']),
        'count': row['total'],
        'pct': round(row['total'] / total_active * 100),
        'icon': cat_icons.get(row['category'], '📋'),
    } for row in category_rows]
    category_data = sorted(rental_rows + other_rows, key=lambda item: -item['count'])[:6]

    top_city_row = visible_qs.values('city').annotate(city_views=Sum('view_count')).order_by('-city_views').first()
    top_city = top_city_row['city'] if top_city_row else None
    top_city_pct = round(top_city_row['city_views'] / (total_views or 1) * 100) if top_city_row and top_city_row['city_views'] else 0

    top_listers = list(
        User.objects.annotate(
            lv=Sum('listings__view_count'),
            lc=Count('listings', filter=Q(listings__status='active'), distinct=True),
            iq=Count('listings__inquiries', distinct=True),
        ).filter(lc__gt=0).order_by('-lv')[:5]
    )

    review_listings = Listing.objects.select_related('owner').filter(Q(status='pending') | Q(status='flagged')).order_by('-created_at')[:10]
    no_photos = visible_qs.annotate(img_count=Count('images')).filter(img_count=0).count()
    no_tags = visible_qs.filter(tags='').count()
    stale = visible_qs.filter(created_at__lte=now - timedelta(days=14), view_count__lt=3).count()

    return {
        'total_users': total_users,
        'new_users_7': new_users_7,
        'new_users_30': new_users_30,
        'recent_users': recent_users,
        'total_listings': total_listings,
        'active_listings': active_count,
        'new_listings_7': new_listings_7,
        'pending_count': pending_count,
        'flagged_count': flagged_count,
        'featured': featured,
        'total_views': total_views,
        'total_messages': total_messages,
        'total_inquiries': total_inquiries,
        'new_inquiries_7': new_inquiries_7,
        'active_listers': active_listers,
        'funnel_steps': funnel_steps,
        'category_data': category_data,
        'top_city': top_city,
        'top_city_pct': top_city_pct,
        'top_listers': top_listers,
        'review_listings': review_listings,
        'no_photos': no_photos,
        'no_tags': no_tags,
        'stale': stale,
    }
