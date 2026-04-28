"""
Event tracker — persists user-listing interactions for ML training.

Usage:
    from listings.services.event_tracker import log_event

    log_event(request, listing, 'click')
    log_event(request, listing, 'contact')
    log_event(request, listing, 'save', search_id=uuid_obj, rank_position=3)
"""
import logging

logger = logging.getLogger(__name__)


def _listing_snapshot(listing):
    return {
        'price':              float(listing.price) if listing.price else None,
        'price_unit':         listing.price_unit,
        'category':           listing.category,
        'property_type':      listing.property_type,
        'accommodation_type': listing.accommodation_type,
        'city':               listing.city,
        'zip_code':           listing.zip_code,
        'bedrooms':           listing.bedrooms,
        'square_footage':     listing.square_footage,
        'year_built':         listing.year_built,
        'hoa_fee':            float(listing.hoa_fee) if listing.hoa_fee else None,
        'bills_included':     listing.bills_included,
        'available_from':     str(listing.available_from) if listing.available_from else None,
        'featured':           listing.featured,
        'status':             listing.status,
    }


def _community_snapshot(community):
    return {
        'name': community.name,
        'community_type': community.community_type,
        'city': community.city,
        'zip_code': community.zip_code,
        'featured': community.featured,
        'status': community.status,
        'community_amenities': community.community_amenities,
        'in_unit_amenities': community.in_unit_amenities,
    }


def _user_snapshot(request):
    """Freeze whatever preference context is available from session / guided-search lead."""
    snapshot = {}

    for key in ('category', 'city', 'min_price', 'max_price',
                'bedrooms', 'property_type', 'tags', 'available_by'):
        val = request.GET.get(key, '') or request.session.get(f'gs_{key}', '')
        if val:
            snapshot[key] = str(val)

    lead_id = request.session.get('gs_lead_id')
    if lead_id:
        try:
            from portal.models import Lead
            lead = Lead.objects.filter(pk=lead_id).values(
                'max_budget', 'city', 'bedrooms', 'property_type',
                'amenities', 'move_in_date', 'priority', 'urgency',
            ).first()
            if lead:
                snapshot.update({k: str(v) for k, v in lead.items() if v is not None})
        except Exception:
            pass

    return snapshot


def _session_key(request):
    if not request.session.session_key:
        request.session.create()
    return request.session.session_key or ''


def log_event(request, listing, event_type,
              search_id=None, rank_position=None, fmm_score=None):
    """
    Persist one user-listing interaction. Never raises — a tracking
    failure must not break the main request.
    """
    from listings.models import UserListingEvent
    try:
        UserListingEvent.objects.create(
            user=request.user if request.user.is_authenticated else None,
            session_key=_session_key(request),
            listing=listing,
            event_type=event_type,
            label=UserListingEvent.LABEL_MAP.get(event_type, 0),
            search_id=search_id,
            rank_position=rank_position,
            fmm_score=fmm_score,
            user_features_snapshot=_user_snapshot(request),
            listing_features_snapshot=_listing_snapshot(listing),
        )
    except Exception:
        logger.exception(
            'log_event failed silently [event=%s listing=%s]',
            event_type, getattr(listing, 'pk', '?'),
        )


def log_community_event(request, community, event_type,
                        search_id=None, rank_position=None, fmm_score=None):
    """
    Persist one user-community interaction. Never raises.
    """
    from listings.models import UserListingEvent
    try:
        UserListingEvent.objects.create(
            user=request.user if request.user.is_authenticated else None,
            session_key=_session_key(request),
            community=community,
            event_type=event_type,
            label=UserListingEvent.LABEL_MAP.get(event_type, 0),
            search_id=search_id,
            rank_position=rank_position,
            fmm_score=fmm_score,
            user_features_snapshot=_user_snapshot(request),
            listing_features_snapshot=_community_snapshot(community),
        )
    except Exception:
        logger.exception(
            'log_community_event failed silently [event=%s community=%s]',
            event_type, getattr(community, 'pk', '?'),
        )


def log_impression_batch(request, impressions, search_id=None):
    """
    Bulk-insert impression events from a client-side batch.

    impressions: list of dicts with keys kind, pk, rank (int), fmm_score (float|None)
    """
    from listings.models import Community, Listing, UserListingEvent
    if not impressions:
        return 0

    listing_pks = [item['pk'] for item in impressions if item.get('kind') == 'listing' and isinstance(item.get('pk'), int)]
    community_pks = [item['pk'] for item in impressions if item.get('kind') == 'community' and isinstance(item.get('pk'), int)]
    listings = {l.pk: l for l in Listing.objects.filter(pk__in=listing_pks)}
    communities = {c.pk: c for c in Community.objects.filter(pk__in=community_pks)}
    user     = request.user if request.user.is_authenticated else None
    skey     = _session_key(request)
    usnap    = _user_snapshot(request)

    events = []
    for item in impressions:
        kind = item.get('kind')
        pk = item.get('pk')
        if kind == 'community':
            community = communities.get(pk)
            if not community:
                continue
            events.append(UserListingEvent(
                user=user,
                session_key=skey,
                community=community,
                event_type=UserListingEvent.IMPRESSION,
                label=0,
                search_id=search_id,
                rank_position=item.get('rank'),
                fmm_score=item.get('fmm_score'),
                user_features_snapshot=usnap,
                listing_features_snapshot=_community_snapshot(community),
            ))
            continue

        listing = listings.get(pk)
        if listing:
            events.append(UserListingEvent(
                user=user,
                session_key=skey,
                listing=listing,
                event_type=UserListingEvent.IMPRESSION,
                label=0,
                search_id=search_id,
                rank_position=item.get('rank'),
                fmm_score=item.get('fmm_score'),
                user_features_snapshot=usnap,
                listing_features_snapshot=_listing_snapshot(listing),
            ))

    if events:
        try:
            UserListingEvent.objects.bulk_create(events)
        except Exception:
            logger.exception('log_impression_batch bulk_create failed')
    return len(events)
