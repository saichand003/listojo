from __future__ import annotations

from datetime import date

from django.db.models import Case, Count, IntegerField, Q, Value, When

from listings.models import Favourite, Listing
from listings.services.matching import explain_match, score_listing
from listings.services.visibility import active_listings


def _parse_int(value: str) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _parse_float(value: str) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_date(value: str) -> date | None:
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def build_listing_search_context(request) -> dict:
    """Shared search/listing context for the consumer discovery experience."""
    listings = active_listings(Listing.objects.select_related('owner').prefetch_related('images'))

    q = request.GET.get('q', '').strip()
    category = request.GET.get('category', '').strip()
    city = request.GET.get('city', '').strip().split(',')[0].strip()
    sort = request.GET.get('sort', 'latest').strip()
    tag = request.GET.get('tag', '').strip()
    min_price = request.GET.get('min_price', '').strip()
    max_price = request.GET.get('max_price', '').strip()
    tags_raw = request.GET.get('tags', '').strip()
    available_by = request.GET.get('available_by', '').strip()
    accommodation_type = request.GET.get('accommodation_type', '').strip()
    property_type = request.GET.get('property_type', '').strip()
    bedrooms = request.GET.get('bedrooms', '').strip()
    fmm = request.GET.get('fmm', '').strip() == '1'

    terms = [t.strip() for t in q.split(',') if t.strip()] if q else []
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
    if accommodation_type:
        listings = listings.filter(accommodation_type=accommodation_type)
    if property_type:
        listings = listings.filter(property_type=property_type)

    bedrooms_int = _parse_int(bedrooms)
    if bedrooms_int is not None:
        listings = listings.filter(bedrooms=bedrooms_int)

    quality_tags = [t.strip() for t in tags_raw.split(',') if t.strip()]
    if quality_tags and not fmm:
        for qt in quality_tags:
            listings = listings.filter(tags__icontains=qt)

    min_price_val = _parse_float(min_price)
    max_price_val = _parse_float(max_price)
    if min_price_val is not None:
        listings = listings.filter(price__gte=min_price_val)
    if max_price_val is not None:
        listings = listings.filter(price__lte=max_price_val)

    avail_date = _parse_date(available_by)
    if avail_date:
        listings = listings.filter(Q(available_from__isnull=True) | Q(available_from__lte=avail_date))

    if terms:
        score_cases = []
        for term in terms:
            score_cases.append(When(title__icontains=term, then=Value(3)))
            score_cases.append(When(tags__icontains=term, then=Value(2)))
            score_cases.append(When(description__icontains=term, then=Value(1)))
        listings = listings.annotate(
            relevance=Case(*score_cases, default=Value(0), output_field=IntegerField())
        )

    if fmm:
        listings = listings.order_by('-featured', '-created_at')
    elif sort == 'price_low':
        listings = listings.order_by('price', '-featured', '-created_at')
    elif sort == 'price_high':
        listings = listings.order_by('-price', '-featured', '-created_at')
    elif sort == 'best_match' and terms:
        listings = listings.order_by('-relevance', '-featured', '-created_at')
    else:
        listings = listings.order_by('-featured', '-created_at')

    if terms and sort == 'latest' and not fmm:
        listings = listings.order_by('-relevance', '-featured', '-created_at')
        sort = 'best_match'

    listing_scores = {}
    listing_score_classes = {}
    listing_reasons = {}
    listing_explanations = {}
    fmm_inputs = None
    fmm_market = None
    near_match_listings = []

    if fmm:
        scored = []
        for listing in list(listings):
            result = score_listing(
                listing,
                max_price=max_price_val,
                requested_tags=quality_tags,
                avail_date=avail_date,
                accommodation_type=accommodation_type,
                property_type=property_type,
                bedrooms=bedrooms_int,
            )
            scored.append((listing, result.pct, result.reasons, result.tag_hits))
        scored.sort(key=lambda item: (-item[1], -item[0].featured, item[0].created_at))

        exact_scored = [item for item in scored if item[1] >= 50]
        near_scored = [item for item in scored if item[1] < 50]
        if not exact_scored and not near_scored:
            near_scored = scored
        elif not exact_scored:
            exact_scored = near_scored[:6]
            near_scored = near_scored[6:]

        listings = [item[0] for item in exact_scored]
        near_match_listings = [item[0] for item in near_scored[:4]]
        listing_scores = {item[0].pk: item[1] for item in scored}
        listing_score_classes = {item[0].pk: 'high' if item[1] >= 85 else 'mid' for item in scored}
        listing_reasons = {item[0].pk: item[2] for item in scored}
        listing_explanations = {
            item[0].pk: explain_match(
                item[0],
                item[2],
                max_price=max_price_val,
                quality_tags=quality_tags,
                accommodation_type=accommodation_type,
                property_type=property_type,
            )
            for item in scored
        }

        total_in_city = active_listings(Listing.objects.all()).filter(city__icontains=city).count() if city else 0
        prices_in_city = list(
            active_listings(Listing.objects.all())
            .filter(city__icontains=city, price__isnull=False)
            .values_list('price', flat=True)
        ) if city else []
        median_price = None
        if prices_in_city:
            ordered = sorted(prices_in_city)
            mid = len(ordered) // 2
            median_price = int(
                ordered[mid] if len(ordered) % 2 else (ordered[mid - 1] + ordered[mid]) / 2
            )

        budget_realistic = None
        if max_price_val and median_price:
            ratio = float(max_price_val) / median_price
            if ratio >= 1.1:
                budget_realistic = 'above'
            elif ratio >= 0.9:
                budget_realistic = 'at'
            else:
                budget_realistic = 'below'

        category_label = dict(Listing.CATEGORY_CHOICES).get(category, '')
        accom_label = dict(Listing.ACCOMMODATION_TYPE_CHOICES).get(accommodation_type, '')
        prop_label = dict(Listing.PROPERTY_TYPE_CHOICES).get(property_type, '')
        avail_display = available_by
        if avail_date:
            avail_display = avail_date.strftime('%b %-d')

        fmm_inputs = {
            'city': city,
            'max_price': max_price,
            'category': category,
            'category_label': category_label,
            'accommodation_type': accommodation_type,
            'accommodation_label': accom_label,
            'property_type': property_type,
            'property_label': prop_label,
            'tags': quality_tags,
            'available_by': avail_display,
        }
        fmm_market = {
            'total_in_city': total_in_city,
            'exact_count': len(exact_scored),
            'near_count': len(near_scored),
            'median_price': median_price,
            'budget_realistic': budget_realistic,
        }

    fav_ids = set()
    if request.user.is_authenticated:
        fav_ids = set(Favourite.objects.filter(user=request.user).values_list('listing_id', flat=True))

    return {
        'listings': list(listings),
        'fav_ids': fav_ids,
        'category_choices': Listing.CATEGORY_CHOICES,
        'wizard_categories': [choice for choice in Listing.CATEGORY_CHOICES if choice[0] in ('rentals', 'properties')],
        'category_counts': dict(Listing.objects.values_list('category').annotate(total=Count('id'))),
        'total_listings': Listing.objects.count(),
        'featured_count': Listing.objects.filter(featured=True).count(),
        'filters': {
            'q': q,
            'category': category,
            'city': city,
            'sort': sort,
            'tag': tag,
            'min_price': min_price,
            'max_price': max_price,
            'tags': tags_raw,
            'available_by': available_by,
        },
        'active_quality_tags': quality_tags,
        'fmm_mode': fmm,
        'fmm_inputs': fmm_inputs,
        'fmm_market': fmm_market,
        'near_match_listings': near_match_listings,
        'listing_scores': listing_scores,
        'listing_score_classes': listing_score_classes,
        'listing_reasons': listing_reasons,
        'listing_explanations': listing_explanations,
    }
