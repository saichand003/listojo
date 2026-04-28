from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from django.db.models import Case, Count, IntegerField, Q, Value, When

from listings.models import Community, Favourite, Listing
from listings.services.matching import explain_community_match, explain_match, score_community, score_listing
from listings.services.visibility import active_listings


COMMUNITY_TYPE_BY_PROPERTY_TYPE = {
    'apartment': 'apartment_complex',
    'condo': 'condo_building',
    'townhouse': 'townhouse_complex',
}


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


@dataclass
class SearchParams:
    q: str = ''
    category: str = ''
    city: str = ''
    sort: str = 'latest'
    tag: str = ''
    min_price: str = ''
    max_price: str = ''
    tags_raw: str = ''
    available_by: str = ''
    accommodation_type: str = ''
    property_type: str = ''
    bedrooms: str = ''
    fmm: bool = False
    # Derived typed values
    terms: list[str] = field(default_factory=list)
    bedrooms_int: int | None = None
    min_price_val: float | None = None
    max_price_val: float | None = None
    avail_date: date | None = None
    quality_tags: list[str] = field(default_factory=list)


def _parse_search_params(request) -> SearchParams:
    p = SearchParams(
        q=request.GET.get('q', '').strip(),
        category=request.GET.get('category', '').strip(),
        city=request.GET.get('city', '').strip().split(',')[0].strip(),
        sort=request.GET.get('sort', 'latest').strip(),
        tag=request.GET.get('tag', '').strip(),
        min_price=request.GET.get('min_price', '').strip(),
        max_price=request.GET.get('max_price', '').strip(),
        tags_raw=request.GET.get('tags', '').strip(),
        available_by=request.GET.get('available_by', '').strip(),
        accommodation_type=request.GET.get('accommodation_type', '').strip(),
        property_type=request.GET.get('property_type', '').strip(),
        bedrooms=request.GET.get('bedrooms', '').strip(),
        fmm=request.GET.get('fmm', '').strip() == '1',
    )
    p.terms = [t.strip() for t in p.q.split(',') if t.strip()] if p.q else []
    p.bedrooms_int = _parse_int(p.bedrooms)
    p.min_price_val = _parse_float(p.min_price)
    p.max_price_val = _parse_float(p.max_price)
    p.avail_date = _parse_date(p.available_by)
    p.quality_tags = [t.strip() for t in p.tags_raw.split(',') if t.strip()]
    return p


def _apply_listing_filters(listings_qs, params: SearchParams, user):
    listings = active_listings(listings_qs)
    listings = listings.filter(parent__isnull=True)
    if user.is_authenticated:
        listings = listings.exclude(owner=user)

    for term in params.terms:
        listings = listings.filter(
            Q(title__icontains=term) | Q(tags__icontains=term) | Q(description__icontains=term)
        )

    if params.category:
        listings = listings.filter(category=params.category)
    if params.city:
        listings = listings.filter(city__icontains=params.city)
    if params.tag:
        listings = listings.filter(tags__icontains=params.tag)
    if params.accommodation_type:
        listings = listings.filter(accommodation_type=params.accommodation_type)
    if params.property_type:
        listings = listings.filter(property_type=params.property_type)
    if params.bedrooms_int is not None:
        listings = listings.filter(bedrooms=params.bedrooms_int)
    if params.quality_tags and not params.fmm:
        for qt in params.quality_tags:
            listings = listings.filter(tags__icontains=qt)
    if params.min_price_val is not None:
        listings = listings.filter(price__gte=params.min_price_val)
    if params.max_price_val is not None:
        listings = listings.filter(price__lte=params.max_price_val)
    if params.avail_date:
        listings = listings.filter(
            Q(available_from__isnull=True) | Q(available_from__lte=params.avail_date)
        )
    return listings


def _apply_listing_ordering(listings_qs, params: SearchParams):
    if params.terms:
        score_cases = []
        for term in params.terms:
            score_cases.append(When(title__icontains=term, then=Value(3)))
            score_cases.append(When(tags__icontains=term, then=Value(2)))
            score_cases.append(When(description__icontains=term, then=Value(1)))
        listings_qs = listings_qs.annotate(
            relevance=Case(*score_cases, default=Value(0), output_field=IntegerField())
        )

    if params.fmm:
        return listings_qs.order_by('-featured', '-created_at')
    if params.sort == 'price_low':
        return listings_qs.order_by('price', '-featured', '-created_at')
    if params.sort == 'price_high':
        return listings_qs.order_by('-price', '-featured', '-created_at')
    if params.sort == 'best_match' and params.terms:
        return listings_qs.order_by('-relevance', '-featured', '-created_at')
    if params.terms and params.sort == 'latest':
        return listings_qs.order_by('-relevance', '-featured', '-created_at')
    return listings_qs.order_by('-featured', '-created_at')


def _matching_communities(user, params: SearchParams) -> list[Community]:
    cqs = Community.objects.filter(status='active').prefetch_related('images', 'floor_plans__units')
    if user.is_authenticated:
        cqs = cqs.exclude(owner=user)
    if params.city:
        cqs = cqs.filter(city__icontains=params.city)
    if params.bedrooms_int is not None:
        cqs = cqs.filter(floor_plans__bedrooms=params.bedrooms_int)
    if params.max_price_val is not None:
        cqs = cqs.filter(
            floor_plans__units__price__lte=params.max_price_val,
            floor_plans__units__status='available',
        )
    if params.category and params.category not in ('rentals', 'properties'):
        return []

    mapped_type = COMMUNITY_TYPE_BY_PROPERTY_TYPE.get(params.property_type)
    if mapped_type:
        cqs = cqs.filter(community_type=mapped_type)
    elif params.property_type:
        return []

    if params.fmm and params.quality_tags:
        for qt in params.quality_tags:
            cqs = cqs.filter(
                Q(community_amenities__icontains=qt)
                | Q(in_unit_amenities__icontains=qt)
                | Q(description__icontains=qt)
            )

    if params.fmm:
        cqs = cqs.order_by('-featured', '-created_at')
    return list(cqs.distinct())


def _compute_market_stats(params: SearchParams) -> dict:
    city = params.city
    all_active = active_listings(Listing.objects.all())
    total_in_city = all_active.filter(city__icontains=city).count() if city else 0
    prices = list(
        all_active.filter(city__icontains=city, price__isnull=False).values_list('price', flat=True)
    ) if city else []

    median_price = None
    if prices:
        ordered = sorted(prices)
        mid = len(ordered) // 2
        median_price = int(ordered[mid] if len(ordered) % 2 else (ordered[mid - 1] + ordered[mid]) / 2)

    budget_realistic = None
    if params.max_price_val and median_price:
        ratio = float(params.max_price_val) / median_price
        budget_realistic = 'above' if ratio >= 1.1 else 'at' if ratio >= 0.9 else 'below'

    return {
        'total_in_city': total_in_city,
        'median_price': median_price,
        'budget_realistic': budget_realistic,
    }


def _score_listings_fmm(listings_qs, params: SearchParams) -> tuple[list, list, dict, dict, dict, dict]:
    scored = []
    for listing in list(listings_qs):
        result = score_listing(
            listing,
            max_price=params.max_price_val,
            requested_tags=params.quality_tags,
            avail_date=params.avail_date,
            accommodation_type=params.accommodation_type,
            property_type=params.property_type,
            bedrooms=params.bedrooms_int,
        )
        scored.append((listing, result.pct, result.reasons, result.tag_hits))
    scored.sort(key=lambda x: (-x[1], -x[0].featured, x[0].created_at))

    exact = [item for item in scored if item[1] >= 50]
    near = [item for item in scored if item[1] < 50]
    if not exact and not near:
        near = scored
    elif not exact:
        exact, near = near[:6], near[6:]

    final_listings = [item[0] for item in exact]
    near_match_listings = [item[0] for item in near[:4]]
    scores = {item[0].pk: item[1] for item in scored}
    score_classes = {item[0].pk: 'high' if item[1] >= 85 else 'mid' for item in scored}
    reasons = {item[0].pk: item[2] for item in scored}
    explanations = {
        item[0].pk: explain_match(
            item[0], item[2],
            max_price=params.max_price_val,
            quality_tags=params.quality_tags,
            accommodation_type=params.accommodation_type,
            property_type=params.property_type,
        )
        for item in scored
    }
    return final_listings, near_match_listings, scores, score_classes, reasons, explanations


def _score_communities_fmm(communities: list, params: SearchParams) -> tuple[list, dict, dict, dict, dict]:
    scored = []
    for community in communities:
        result = score_community(
            community,
            max_price=params.max_price_val,
            requested_tags=params.quality_tags,
            property_type=params.property_type,
            bedrooms=params.bedrooms_int,
        )
        scored.append((community, result.pct, result.reasons, result.tag_hits))
    scored.sort(key=lambda x: (-x[1], -x[0].featured, x[0].created_at))

    ranked = [item[0] for item in scored]
    scores = {item[0].pk: item[1] for item in scored}
    score_classes = {item[0].pk: 'high' if item[1] >= 85 else 'mid' for item in scored}
    reasons = {item[0].pk: item[2] for item in scored}
    explanations = {
        item[0].pk: explain_community_match(
            item[0], item[2],
            max_price=params.max_price_val,
            quality_tags=params.quality_tags,
            property_type=params.property_type,
        )
        for item in scored
    }
    return ranked, scores, score_classes, reasons, explanations


def _build_fmm_context(listings_qs, communities: list, params: SearchParams) -> dict:
    (
        listings, near_match_listings,
        listing_scores, listing_score_classes, listing_reasons, listing_explanations,
    ) = _score_listings_fmm(listings_qs, params)

    (
        communities, community_scores, community_score_classes,
        community_reasons, community_explanations,
    ) = _score_communities_fmm(communities, params)

    market = _compute_market_stats(params)
    avail_display = params.avail_date.strftime('%b %-d') if params.avail_date else params.available_by

    return {
        'listings': listings,
        'near_match_listings': near_match_listings,
        'communities': communities,
        'listing_scores': listing_scores,
        'listing_score_classes': listing_score_classes,
        'listing_reasons': listing_reasons,
        'listing_explanations': listing_explanations,
        'community_scores': community_scores,
        'community_score_classes': community_score_classes,
        'community_reasons': community_reasons,
        'community_explanations': community_explanations,
        'fmm_inputs': {
            'city': params.city,
            'max_price': params.max_price,
            'category': params.category,
            'category_label': dict(Listing.CATEGORY_CHOICES).get(params.category, ''),
            'accommodation_type': params.accommodation_type,
            'accommodation_label': dict(Listing.ACCOMMODATION_TYPE_CHOICES).get(params.accommodation_type, ''),
            'property_type': params.property_type,
            'property_label': dict(Listing.PROPERTY_TYPE_CHOICES).get(params.property_type, ''),
            'tags': params.quality_tags,
            'available_by': avail_display,
        },
        'fmm_market': {
            'total_in_city': market['total_in_city'],
            'exact_count': len(listings) + len(communities),
            'near_count': len(near_match_listings),
            'median_price': market['median_price'],
            'budget_realistic': market['budget_realistic'],
        },
    }


def build_listing_search_context(request) -> dict:
    """Shared search/listing context for the consumer discovery experience."""
    params = _parse_search_params(request)

    base_qs = Listing.objects.select_related('owner').prefetch_related('images')
    listings_qs = _apply_listing_filters(base_qs, params, request.user)
    listings_qs = _apply_listing_ordering(listings_qs, params)

    sort = 'best_match' if (params.terms and params.sort == 'latest' and not params.fmm) else params.sort

    communities = _matching_communities(request.user, params)

    if params.fmm:
        fmm = _build_fmm_context(listings_qs, communities, params)
        listings = fmm.pop('listings')
        communities = fmm.pop('communities')
    else:
        fmm = {}
        listings = list(listings_qs)

    fav_ids = set()
    if request.user.is_authenticated:
        fav_ids = set(Favourite.objects.filter(user=request.user).values_list('listing_id', flat=True))

    return {
        'listings': listings,
        'total_matches': len(listings) + len(communities),
        'fav_ids': fav_ids,
        'category_choices': Listing.CATEGORY_CHOICES,
        'wizard_categories': [c for c in Listing.CATEGORY_CHOICES if c[0] in ('rentals', 'properties')],
        'category_counts': dict(Listing.objects.values_list('category').annotate(total=Count('id'))),
        'total_listings': Listing.objects.count(),
        'featured_count': Listing.objects.filter(featured=True).count(),
        'filters': {
            'q': params.q,
            'category': params.category,
            'city': params.city,
            'sort': sort,
            'tag': params.tag,
            'min_price': params.min_price,
            'max_price': params.max_price,
            'tags': params.tags_raw,
            'available_by': params.available_by,
        },
        'active_quality_tags': params.quality_tags,
        'fmm_mode': params.fmm,
        'fmm_inputs': fmm.get('fmm_inputs'),
        'fmm_market': fmm.get('fmm_market'),
        'near_match_listings': fmm.get('near_match_listings', []),
        'listing_scores': fmm.get('listing_scores', {}),
        'listing_score_classes': fmm.get('listing_score_classes', {}),
        'listing_reasons': fmm.get('listing_reasons', {}),
        'listing_explanations': fmm.get('listing_explanations', {}),
        'community_scores': fmm.get('community_scores', {}),
        'community_score_classes': fmm.get('community_score_classes', {}),
        'community_reasons': fmm.get('community_reasons', {}),
        'community_explanations': fmm.get('community_explanations', {}),
        'communities': communities,
    }
