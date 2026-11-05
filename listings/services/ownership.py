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


def is_partner(user) -> bool:
    """
    May this person list and run multi-family communities?

    Communities are partner inventory: publishing one asserts authority over a
    whole property and its media, which is why partner accounts are approved
    by staff (partners.PartnerApplication) rather than self-serve. An
    individual landlord posts listings, not communities. Superusers pass so
    support can see what a partner sees.
    """
    if not user or not user.is_authenticated:
        return False
    return user.is_superuser or Membership.objects.filter(user=user).exists()


def is_partner_member(user) -> bool:
    """
    Does this person belong to a partner organization?

    Unlike is_partner, a superuser does not count. This decides which side of
    the product someone is on — a partner manages a portfolio through the
    partner portal and does not post one-off listings — and an admin needs to
    reach both sides.
    """
    if not user or not user.is_authenticated:
        return False
    return Membership.objects.filter(user=user).exists()


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
