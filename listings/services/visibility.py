from __future__ import annotations

from datetime import date

from django.db.models import Q


def active_listings(queryset=None):
    """Return listings that are publicly visible right now."""
    from listings.models import Listing

    qs = queryset if queryset is not None else Listing.objects.all()
    today = date.today()
    return qs.filter(status='active').filter(
        Q(expires_at__isnull=True) | Q(expires_at__gte=today)
    )


def is_visible(listing) -> bool:
    """Return True when a listing should be visible to consumers and agents."""
    if listing.status != 'active':
        return False
    if listing.expires_at and listing.expires_at < date.today():
        return False
    return True
