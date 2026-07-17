"""
Saved-search alerts — find new listings matching a user's saved guided search
and notify them by email + SMS.

Entry point: send_alerts_for_all() — called by the `send_saved_search_alerts`
management command (run on a schedule). It is idempotent: each search has a
`last_alerted_at` watermark so a listing is only ever alerted once.
"""
from __future__ import annotations

import logging

from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone

from listings.models import SavedSearch
from listings.services.visibility import active_listings
from listojo.services.notifications import notify_user

logger = logging.getLogger(__name__)

# How many listings to itemise in a single alert before summarising.
_MAX_ITEMS = 5
# How many listing cards to render in the HTML email.
_MAX_CARDS = 6


def _listing_image_url(lst, site_url: str) -> str:
    """Absolute URL to a listing's primary photo, or '' if none."""
    img = lst.images.first()
    file = img.image if img else (lst.image or None)
    if not file:
        return ''
    try:
        url = file.url
    except Exception:
        return ''
    if url.startswith(('http://', 'https://')):
        return url
    return f"{site_url.rstrip('/')}/{url.lstrip('/')}"


def _listing_specs(lst) -> str:
    """'2 Beds  |  1 Bath  |  1,080 sqft' — omits missing pieces."""
    parts = []
    if lst.bedrooms is not None:
        parts.append(f"{lst.bedrooms} Bed{'s' if lst.bedrooms != 1 else ''}")
    if lst.bathrooms is not None:
        b = int(lst.bathrooms) if lst.bathrooms == int(lst.bathrooms) else lst.bathrooms
        parts.append(f"{b} Bath{'s' if b != 1 else ''}")
    if lst.square_footage:
        parts.append(f"{lst.square_footage:,} sqft")
    return '  |  '.join(parts)


def _card_context(lst, search: SavedSearch, site_url: str) -> dict:
    """Build the per-listing dict the HTML template renders as a card."""
    if lst.price:
        unit = '/mo' if search.search_type != 'buy' else ''
        price_display = f'${int(lst.price):,}{unit}'
    else:
        price_display = 'Contact for price'
    address = ', '.join(p for p in [lst.address_line, lst.city] if p) or lst.city
    return {
        'title': lst.title,
        'price_display': price_display,
        'specs': _listing_specs(lst),
        'address': address,
        'url': f'{site_url}{reverse("listing_detail", args=[lst.pk])}',
        'image_url': _listing_image_url(lst, site_url),
    }


def _build_html_body(search: SavedSearch, listings: list, site_url: str) -> str:
    """Render the Zumper-style HTML email for a batch of new matches."""
    n = len(listings)
    kind = 'home' if search.search_type == 'buy' else 'rental'
    context = {
        'subject': f'{n} new {kind}{"s" if n != 1 else ""} matching your search',
        'preheader': f'Fresh {kind} matches for your saved search — explore them on Listojo.',
        'headline': 'More of our favorite listings',
        'intro_lead': f'{n} new {kind}{"s" if n != 1 else ""} just matched your saved search',
        'intro_tail': 'Explore them and many others fresh every day on Listojo.',
        'city': search.city,
        'items': [_card_context(l, search, site_url) for l in listings[:_MAX_CARDS]],
        'results_url': f'{site_url}{reverse("listing_list")}?{search.as_url_params()}',
        'prefs_url': f'{site_url}{reverse("update_notification_prefs")}',
        'unsubscribe_url': f'{site_url}{reverse("update_notification_prefs")}',
        'site_url': site_url,
    }
    return render_to_string('listings/emails/saved_search_alert.html', context)


def matching_listings_for_search(search: SavedSearch, since=None):
    """
    Return active listings matching a SavedSearch's criteria, newest first.
    When `since` is given, only listings created strictly after it are returned.
    """
    qs = active_listings().filter(parent__isnull=True).exclude(owner=search.user)

    # Rent vs Buy
    if search.search_type == 'buy':
        qs = qs.filter(category='properties')
    else:
        qs = qs.exclude(category='properties')

    if search.city:
        qs = qs.filter(city__icontains=search.city)
    if search.max_budget is not None:
        qs = qs.filter(price__lte=search.max_budget)
    if search.bedrooms:
        # "at least N bedrooms" — the usual search convention
        qs = qs.filter(bedrooms__gte=search.bedrooms)
    if search.property_type:
        qs = qs.filter(property_type=search.property_type)
    if search.accommodation_type:
        qs = qs.filter(accommodation_type=search.accommodation_type)

    if since is not None:
        qs = qs.filter(created_at__gt=since)

    return qs.order_by('-created_at')


def _build_alert_bodies(search: SavedSearch, listings: list, site_url: str):
    """Return (subject, email_body, sms_body) for a batch of new matches."""
    n = len(listings)
    where = f' in {search.city}' if search.city else ''
    kind = 'home' if search.search_type == 'buy' else 'rental'
    subject = f'{n} new {kind}{"s" if n != 1 else ""}{where} matching your search'

    lines = [f'Hi {search.user.get_full_name() or search.user.email or search.user.username},', '',
             f'{n} new listing{"s" if n != 1 else ""} just matched your saved {kind} search'
             f'{where}:', '']
    for lst in listings[:_MAX_ITEMS]:
        price = f'${int(lst.price):,}' if lst.price else 'Contact for price'
        unit = '/mo' if search.search_type != 'buy' else ''
        url = f'{site_url}{reverse("listing_detail", args=[lst.pk])}'
        lines.append(f'• {lst.title} — {price}{unit} — {lst.city}')
        lines.append(f'  {url}')
    if n > _MAX_ITEMS:
        lines.append(f'…and {n - _MAX_ITEMS} more.')
    results_url = f'{site_url}{reverse("listing_list")}?{search.as_url_params()}'
    lines += ['', f'See all matches: {results_url}', '',
              'You’re receiving this because you saved a search on Listojo.']
    email_body = '\n'.join(lines)

    first = listings[0]
    fprice = f'${int(first.price):,}' if first.price else 'See price'
    sms_body = (
        f'Listojo: {n} new {kind}{"s" if n != 1 else ""}{where} match your search. '
        f'e.g. {first.title} ({fprice}). View: {results_url}'
    )
    return subject, email_body, sms_body


def send_alerts_for_search(search: SavedSearch, site_url: str) -> int:
    """
    Find new matches for one search, notify the user, advance the watermark.
    Returns the number of new listings alerted (0 if none / alerts off).
    """
    if not search.alerts_enabled:
        return 0

    since = search.last_alerted_at
    matches = list(matching_listings_for_search(search, since=since)[:50])

    # Always advance the watermark so we don't re-scan old rows next run.
    search.last_alerted_at = timezone.now()
    search.save(update_fields=['last_alerted_at'])

    if not matches:
        return 0

    subject, email_body, sms_body = _build_alert_bodies(search, matches, site_url)
    html_body = _build_html_body(search, matches, site_url)
    notify_user(search.user, subject=subject, email_body=email_body,
                html_body=html_body, sms_body=sms_body)
    logger.info('saved-search alert: %s match(es) to %s', len(matches), search.user)
    return len(matches)


def send_alerts_for_all(site_url: str) -> dict:
    """Process every alert-enabled saved search. Returns summary counts."""
    searches = SavedSearch.objects.filter(alerts_enabled=True).select_related('user')
    total_listings, notified = 0, 0
    for search in searches.iterator():
        try:
            n = send_alerts_for_search(search, site_url)
        except Exception:
            logger.exception('send_alerts_for_search failed for search #%s', search.pk)
            continue
        if n:
            total_listings += n
            notified += 1
    return {'searches': searches.count(), 'notified': notified, 'listings': total_listings}
