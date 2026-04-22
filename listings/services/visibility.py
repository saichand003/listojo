"""
Listing visibility / eligibility rules.

Any code that needs to know "is this listing publicly visible?" must go
through this module. Prevents the expires_at + status filter from being
duplicated across consumer search, agent matching, and shortlist building.
"""
from __future__ import annotations

from datetime import date

from django.db.models import Q, QuerySet


def active_listings(queryset=None):
    """
    Return a queryset of listings that are publicly visible:
      - status = 'active'
      - not expired (expires_at is null OR expires_at >= today)

    Pass an existing queryset to further filter it, or omit to start fresh.
    """
    from listings.models import Listing

    qs = queryset if queryset is not None else Listing.objects.all()
    today = date.today()
    return qs.filter(status='active').filter(
        Q(expires_at__isnull=True) | Q(expires_at__gte=today)
    )


def is_visible(listing) -> bool:
    """Return True if a single listing is currently publicly visible."""
    if listing.status != 'active':
        return False
    if listing.expires_at and listing.expires_at < date.today():
        return False
    return True
