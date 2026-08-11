"""
Who may edit a listing or community.

Two legitimate kinds of ownership exist, and collapsing them was the original
mistake:

    individual landlord  -> owns their listing personally (`owner`)
    property manager     -> the *company* holds it (`organization` / `managed_by`)

So this is not "replace owner with organization everywhere". Native listings
posted by a person stay person-owned. Partner inventory belongs to the company,
and any member of that company may edit it.
"""
from __future__ import annotations

from partners.models import Membership


def user_organization_ids(user) -> list[int]:
    """Organizations this user belongs to. Empty for individual landlords."""
    if not user or not user.is_authenticated:
        return []
    return list(Membership.objects.filter(user=user).values_list('organization_id', flat=True))


def can_edit_listing(user, listing) -> bool:
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    if listing.organization_id:
        return listing.organization_id in user_organization_ids(user)
    return listing.owner_id == user.pk


def can_edit_community(user, community) -> bool:
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    if community.managed_by_id:
        return community.managed_by_id in user_organization_ids(user)
    return community.owner_id == user.pk


def editable_listings(user, queryset):
    """Filter a Listing queryset to rows `user` may edit."""
    from django.db.models import Q
    if not user or not user.is_authenticated:
        return queryset.none()
    if user.is_superuser:
        return queryset
    return queryset.filter(
        Q(owner=user) | Q(organization_id__in=user_organization_ids(user)))


def editable_communities(user, queryset):
    """Filter a Community queryset to rows `user` may edit."""
    from django.db.models import Q
    if not user or not user.is_authenticated:
        return queryset.none()
    if user.is_superuser:
        return queryset
    return queryset.filter(
        Q(owner=user) | Q(managed_by_id__in=user_organization_ids(user)))
