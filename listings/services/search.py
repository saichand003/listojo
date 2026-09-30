from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from django.db.models import Case, Count, IntegerField, Q, Value, When

from listings.models import Community, Favourite, Listing
from listings.services.fit import build_reports
from listings.services.match_prefs import MatchPrefs, remember, resolve_match_prefs
from listings.services.matching import match_badge_class
from listings.services.visibility import active_listings


COMMUNITY_TYPE_BY_PROPERTY_TYPE = {
    'apartment': 'apartment_complex',
    'condo': 'condo_building',
    'townhouse': 'townhouse_complex',
}


def live_inventory_count() -> int:
    """
    Everything a renter or buyer can open right now: visible stand-alone
    listings plus active communities. The home page, the guided-search rail and
    the results page all report inventory, so they share this one definition.
    Leaving communities out is what made the rail say "1 of 1 live listings"
    while the Rent tab showed three.
    """
    return (
        active_listings(Listing.objects.filter(parent__isnull=True)).count()
        + Community.objects.filter(status='active').count()
    )


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
    priority: str = ''
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
        priority=request.GET.get('priority', '').strip(),
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
    # "whole" = an entire place: anything not listed as a single room (a blank
    # type is an older whole-home listing). "room" = a room to rent, whether it
    # was posted under Roommates or as a room under Rentals, so the room tab
    # and the rentals tab can never both miss (or both show) the same bedroom.
    if params.accommodation_type == 'whole':
        listings = listings.exclude(accommodation_type='room').exclude(category='roommates')
    elif params.accommodation_type == 'room':
        listings = listings.filter(Q(accommodation_type='room') | Q(category='roommates'))
    elif params.accommodation_type:
        listings = listings.filter(accommodation_type=params.accommodation_type)
    if params.property_type:
        listings = listings.filter(property_type=params.property_type)
    if params.bedrooms_int is not None:
        listings = listings.filter(bedrooms=params.bedrooms_int)
    if params.quality_tags and not params.fmm:
        # Amenity columns join `tags` here for the same reason the community
        # branch below searches them: the same fact can be typed as a filter
        # tag or entered in a catalogue, and a renter searching "balcony"
        # should not care which box the seller used.
        for qt in params.quality_tags:
            listings = listings.filter(
                Q(tags__icontains=qt)
                | Q(community_amenities__icontains=qt)
                | Q(in_unit_amenities__icontains=qt)
            )
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
    cqs = Community.objects.filter(status='active').select_related('nearest_downtown').prefetch_related(
        'images', 'floor_plans__units', 'nearby_groceries__store', 'nearby_transit__station')
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
    # Communities are rental inventory, so the Buy tab excludes them — but an
    # unset category means "no filter", not "not rentals". Treating blank as a
    # mismatch hid every community from the default /listings/ view, which is
    # exactly where a renter lands after signing in.
    if params.category and params.category != 'rentals':
        return []
    # A community rents whole units, never a single room.
    if params.accommodation_type == 'room':
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


def _prefs_from_params(params: SearchParams) -> MatchPrefs:
    return MatchPrefs(
        max_price=params.max_price_val,
        tags=params.quality_tags,
        bedrooms=params.bedrooms_int,
        property_type=params.property_type,
        accommodation_type=params.accommodation_type,
        avail_date=params.avail_date,
        priority=params.priority,
        source='your search',
    )


def _score_items(items, score_fn) -> dict:
    """
    Score each item once and key the badge by pk. Items with no score (nothing
    to measure) are left out, so the card shows no badge.
    """
    out = {'scores': {}, 'classes': {}}
    for item in items:
        result = score_fn(item)
        if result.pct is None:
            continue
        out['scores'][item.pk] = result.pct
        out['classes'][item.pk] = match_badge_class(result.pct)
    return out


def _score_listings_fmm(listings_qs, prefs: MatchPrefs) -> tuple[list, list, dict]:
    listings = list(listings_qs)
    scored = _score_items(listings, prefs.score)
    pct = scored['scores']
    # Featured only breaks ties between equal scores; it never lifts a score.
    if not pct:
        # Nothing to measure: no exact/near split to make.
        return listings, [], scored
    listings.sort(key=lambda l: (-pct.get(l.pk, 0), -l.featured, l.created_at))

    exact = [l for l in listings if pct.get(l.pk, 0) >= 50]
    near = [l for l in listings if pct.get(l.pk, 0) < 50]
    if not exact:
        exact, near = near[:6], near[6:]
    return exact, near[:4], scored


def _score_communities_fmm(communities: list, prefs: MatchPrefs) -> tuple[list, dict]:
    scored = _score_items(communities, prefs.score_community)
    pct = scored['scores']
    ranked = sorted(communities, key=lambda c: (-pct.get(c.pk, 0), -c.featured, c.created_at))
    return ranked, scored


def _score_context(listing_scored: dict, community_scored: dict) -> dict:
    ctx = {}
    for prefix, scored in (('listing', listing_scored), ('community', community_scored)):
        ctx[f'{prefix}_scores'] = scored.get('scores', {})
        ctx[f'{prefix}_score_classes'] = scored.get('classes', {})
    return ctx


def _build_fmm_context(listings_qs, communities: list, params: SearchParams) -> dict:
    prefs = _prefs_from_params(params)
    listings, near_match_listings, listing_scored = _score_listings_fmm(listings_qs, prefs)
    communities, community_scored = _score_communities_fmm(communities, prefs)

    market = _compute_market_stats(params)
    avail_display = params.avail_date.strftime('%b %-d') if params.avail_date else params.available_by

    return {
        'prefs': prefs,
        'listings': listings,
        'near_match_listings': near_match_listings,
        'communities': communities,
        'scores': _score_context(listing_scored, community_scored),
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


def live_match_preview(request, limit: int = 3) -> dict:
    """
    Real counts and real listings for the guided-search intelligence rail,
    from whatever criteria have been chosen so far.

    The rail is meant to say "here is what your answers match right now", so it
    has to run the same filters the results page runs. It reuses the same
    parser, so the preview and the results it promises cannot drift apart.
    """
    params = _parse_search_params(request)
    qs = Listing.objects.select_related('owner').prefetch_related('images')
    qs = _apply_listing_filters(qs, params, request.user)
    qs = _apply_listing_ordering(qs, params)
    # The same communities the results page shows for these answers — the
    # rail used to count listings only, so it disagreed with the Rent tab.
    communities = _matching_communities(request.user, params)

    total = qs.count() + len(communities)
    # Communities first, as on the results page, then listings, up to `limit`.
    top = communities[:limit] + list(qs[:max(0, limit - len(communities))])

    return {
        'total': total,
        # Total live inventory, so the rail can say "N of M" rather than
        # reporting a count with nothing to scale it against.
        'inventory': live_inventory_count(),
        'listings': top,
        'params': params,
    }


def build_listing_search_context(request) -> dict:
    """Shared search/listing context for the consumer discovery experience."""
    params = _parse_search_params(request)

    # The Fit Report reads each card's nearby places; prefetch them so a page
    # of cards is a handful of queries, not a handful per card.
    base_qs = Listing.objects.select_related('owner', 'nearest_downtown').prefetch_related(
        'images', 'nearby_schools__school', 'nearby_groceries__store', 'nearby_transit__station')
    listings_qs = _apply_listing_filters(base_qs, params, request.user)
    listings_qs = _apply_listing_ordering(listings_qs, params)

    sort = 'best_match' if (params.terms and params.sort == 'latest' and not params.fmm) else params.sort

    communities = _matching_communities(request.user, params)

    if params.fmm:
        fmm = _build_fmm_context(listings_qs, communities, params)
        listings = fmm.pop('listings')
        communities = fmm.pop('communities')
        prefs = fmm.pop('prefs')
        # So the detail page a card links to scores against the same criteria.
        if prefs.has_criteria:
            remember(request, prefs)
        scores = fmm.pop('scores')
        fit_reports = {
            'listing_fit': build_reports(listings + fmm['near_match_listings'], prefs),
            'community_fit': build_reports(communities, prefs),
        }
    else:
        fmm = {}
        listings = list(listings_qs)
        # Browsing keeps its own order; if the visitor has told us what they
        # want, the cards still show how well each one fits.
        prefs = resolve_match_prefs(request)
        if prefs:
            scores = _score_context(
                _score_items(listings, prefs.score),
                _score_items(communities, prefs.score_community),
            )
            fit_reports = {
                'listing_fit': build_reports(listings, prefs),
                'community_fit': build_reports(communities, prefs),
            }
        else:
            scores = _score_context({}, {})
            fit_reports = {'listing_fit': {}, 'community_fit': {}}

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
            'bedrooms': params.bedrooms,
            'tags': params.tags_raw,
            'available_by': params.available_by,
        },
        'active_quality_tags': params.quality_tags,
        'fmm_mode': params.fmm,
        'fmm_inputs': fmm.get('fmm_inputs'),
        'fmm_market': fmm.get('fmm_market'),
        'near_match_listings': fmm.get('near_match_listings', []),
        **scores,
        **fit_reports,
        # Drives the "Get your match score" chip and the sheet's defaults.
        'match_prefs': prefs if prefs and prefs.has_criteria else None,
        'communities': communities,
    }
