from __future__ import annotations


def approve(listing) -> None:
    listing.status = 'active'
    listing.save(update_fields=['status'])


def reject(listing) -> None:
    listing.status = 'draft'
    listing.save(update_fields=['status'])


def flag(listing) -> None:
    listing.status = 'flagged'
    listing.save(update_fields=['status'])


def toggle_featured(listing) -> None:
    listing.featured = not listing.featured
    listing.save(update_fields=['featured'])
