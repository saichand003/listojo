"""
Partner inventory ingestion — adapter interface + canonical model + upsert.

The shape here follows the implementation blueprint: every supply path
(CSV today; XML, JSON, MITS, custom partner APIs later) parses into one
`CanonicalListing`, and everything downstream — validation, upsert, safe
deactivation — runs identically regardless of where the data came from.

Adding a format means writing one `PartnerAdapter` subclass. It does not mean
touching `import_partner_inventory()`.

    adapter = CsvAdapter(open('inventory.csv'))
    result  = import_partner_inventory(adapter, organization=acme_org)
"""
from __future__ import annotations

import csv
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, fields
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import IO, Iterator

from django.db import transaction
from django.utils import timezone

from listings.models import Community, CommunityImage, FloorPlan, Listing, Unit
from partners.models import ManagementAssignment, Organization, SourceRecordMap

logger = logging.getLogger(__name__)

# A run that would deactivate more than this share of a partner's live
# inventory is treated as a broken upload, not a real shrink. Blueprint §13:
# "A failed or partial partner feed must never mass-deactivate inventory."
DEFAULT_DEACTIVATION_CEILING = 0.30


# ─────────────────────────────────────────────────────────────────────────────
# Canonical model — blueprint §11, trimmed to what Listing can store today
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class CanonicalListing:
    """One rentable unit, normalized. Adapters produce these; nothing else does."""

    source_listing_id: str
    address_line: str
    city: str
    price: Decimal

    title: str = ''
    description: str = ''
    state: str = 'TX'
    zip_code: str = ''
    price_unit: str = 'mo'
    bedrooms: int | None = None
    bathrooms: Decimal | None = None
    square_footage: int | None = None
    year_built: int | None = None
    property_type: str = ''
    accommodation_type: str = ''
    security_deposit: Decimal | None = None
    bills_included: bool = False
    available_from: date | None = None
    contact_phone: str = ''
    virtual_tour_url: str = ''
    tags: str = ''
    photo_urls: list[str] = field(default_factory=list)

    def as_listing_fields(self) -> dict:
        """Model kwargs for this record. Excludes identity and media."""
        skip = {'source_listing_id', 'photo_urls'}
        return {f.name: getattr(self, f.name) for f in fields(self) if f.name not in skip}


@dataclass
class CanonicalUnit:
    """
    One rentable unit inside a managed property — blueprint §11's
    "property, floorplan, unit hierarchy where applicable".

    Imports as Community → FloorPlan → Unit, which is what renders the
    Community chip in search and the floor-plan/unit tables on the detail page.
    Community and floor-plan fields repeat on every row of the same property;
    that is how a flat CSV expresses a tree, and the importer de-duplicates.
    """

    community_ref: str
    community_name: str
    floor_plan_name: str
    unit_number: str
    bedrooms: int
    price: Decimal

    source_unit_id: str = ''
    bathrooms: Decimal | None = None
    square_footage: int | None = None
    floor: int | None = None
    available_from: date | None = None
    unit_status: str = 'available'

    community_address_line: str = ''
    community_city: str = ''
    community_state: str = 'TX'
    community_zip: str = ''
    community_description: str = ''
    community_type: str = ''
    community_amenities: str = ''
    in_unit_amenities: str = ''
    contact_phone: str = ''
    photo_urls: list[str] = field(default_factory=list)

    def __post_init__(self):
        # The unit number is the partner's identifier unless they supply another.
        self.source_unit_id = self.source_unit_id or self.unit_number

    def community_fields(self) -> dict:
        return {
            'name': self.community_name,
            'address_line': self.community_address_line,
            'city': self.community_city,
            'state': self.community_state,
            'zip_code': self.community_zip,
            'description': self.community_description,
            'community_type': self.community_type,
            'community_amenities': self.community_amenities,
            'in_unit_amenities': self.in_unit_amenities,
            'contact_phone': self.contact_phone,
        }

    def floor_plan_fields(self) -> dict:
        return {
            'bedrooms': self.bedrooms,
            'bathrooms': self.bathrooms if self.bathrooms is not None else Decimal('1.0'),
            'square_footage': self.square_footage,
        }

    def unit_fields(self) -> dict:
        return {
            'unit_number': self.unit_number,
            'floor': self.floor,
            'price': self.price,
            'available_from': self.available_from,
            'status': self.unit_status,
            'deactivation_pending_since': None,
        }


@dataclass
class Rejection:
    """A row that could not be imported, kept for the partner-facing report."""
    row_number: int
    reason: str
    raw: dict


@dataclass
class ImportResult:
    created: int = 0
    updated: int = 0
    pending_deactivation: int = 0
    deactivated: int = 0
    photos_saved: int = 0
    communities: int = 0
    floor_plans: int = 0
    units: int = 0
    units_updated: int = 0
    rejections: list[Rejection] = field(default_factory=list)
    aborted_reason: str = ''

    @property
    def ok(self) -> bool:
        return not self.aborted_reason

    def summary(self) -> str:
        if self.aborted_reason:
            return f'ABORTED — {self.aborted_reason}'
        parts = [f'{self.created} created', f'{self.updated} updated']
        if self.communities or self.units or self.units_updated:
            parts.append(f'{self.communities} new communities / {self.floor_plans} new floor '
                         f'plans / {self.units} new units / {self.units_updated} units updated')
        parts += [f'{self.pending_deactivation} pending deactivation',
                  f'{self.deactivated} deactivated',
                  f'{self.photos_saved} photos',
                  f'{len(self.rejections)} rejected']
        return ', '.join(parts)


# ─────────────────────────────────────────────────────────────────────────────
# Adapter interface
# ─────────────────────────────────────────────────────────────────────────────

class PartnerAdapter(ABC):
    """
    Turns one partner's format into `CanonicalListing` records.

    Adapters parse and normalize. They do not touch the database, and they do
    not decide what happens to rows they cannot read — they report those as
    rejections and keep going, so one malformed row never costs a partner the
    rest of their upload.
    """

    #: Short label used in logs and the import report.
    format_name: str = 'unknown'

    @abstractmethod
    def iter_listings(self) -> Iterator[tuple[int, CanonicalListing | None, Rejection | None]]:
        """Yield (row_number, listing, rejection). Exactly one of the last two is set."""
        raise NotImplementedError


class CsvAdapter(PartnerAdapter):
    """
    Listojo's CSV template — see `docs/partner-csv-template.csv`.

    Unknown columns are ignored rather than rejected: partners export from a PMS
    and routinely carry extra fields, and failing their upload over a column we
    don't need would be hostile.
    """

    format_name = 'csv'

    #: Standalone rentals — a house, duplex or condo with no shared property.
    REQUIRED_COLUMNS = ('source_listing_id', 'address_line', 'city', 'price')
    #: Units inside a managed property. Presence of `community_ref` on a row
    #: selects this shape, so one file can carry both.
    UNIT_REQUIRED_COLUMNS = ('community_ref', 'community_name', 'floor_plan_name',
                             'unit_number', 'bedrooms', 'price')

    def __init__(self, stream: IO[str]):
        self.stream = stream

    def iter_listings(self):
        reader = csv.DictReader(self.stream)
        columns = reader.fieldnames or []

        # A file is valid if it can express at least one shape. Rows are then
        # checked individually, so a community row in a flat file still fails
        # loudly rather than importing half-populated.
        flat_missing = [c for c in self.REQUIRED_COLUMNS if c not in columns]
        unit_missing = [c for c in self.UNIT_REQUIRED_COLUMNS if c not in columns]
        if flat_missing and unit_missing:
            yield 0, None, Rejection(
                0,
                f'Missing required column(s): {", ".join(flat_missing)} '
                f'(for standalone rentals) or {", ".join(unit_missing)} '
                f'(for units in a community)',
                {})
            return

        for row_number, raw in enumerate(reader, start=2):   # row 1 is the header
            row = {k.strip(): (v or '').strip() for k, v in raw.items() if k}
            try:
                record = (self._to_unit(row) if row.get('community_ref')
                          else self._to_canonical(row))
                yield row_number, record, None
            except ValueError as exc:
                yield row_number, None, Rejection(row_number, str(exc), row)

    def _to_unit(self, row: dict) -> CanonicalUnit:
        for column in self.UNIT_REQUIRED_COLUMNS:
            if not row.get(column):
                raise ValueError(f'{column} is required for a community unit row')

        price = _decimal(row['price'], 'price')
        if price <= 0:
            raise ValueError('price must be greater than zero')

        status = (row.get('unit_status') or 'available').lower()
        if status not in ('available', 'occupied', 'coming_soon'):
            raise ValueError(f'unit_status "{status}" must be available, occupied or coming_soon')

        return CanonicalUnit(
            community_ref=row['community_ref'],
            community_name=row['community_name'],
            floor_plan_name=row['floor_plan_name'],
            unit_number=row['unit_number'],
            bedrooms=_int(row['bedrooms'], 'bedrooms'),
            price=price,
            source_unit_id=row.get('source_unit_id', ''),
            bathrooms=_decimal(row.get('bathrooms'), 'bathrooms', required=False),
            square_footage=_int(row.get('square_footage'), 'square_footage'),
            floor=_int(row.get('floor'), 'floor'),
            available_from=_date(row.get('available_from')),
            unit_status=status,
            community_address_line=row.get('community_address_line', ''),
            community_city=row.get('community_city') or row.get('city', ''),
            community_state=row.get('community_state') or row.get('state') or 'TX',
            community_zip=row.get('community_zip') or row.get('zip_code', ''),
            community_description=row.get('community_description', ''),
            community_type=row.get('community_type', ''),
            community_amenities=_commas(row.get('community_amenities', '')),
            in_unit_amenities=_commas(row.get('in_unit_amenities', '')),
            contact_phone=row.get('contact_phone', ''),
            photo_urls=[u.strip() for u in row.get('photo_urls', '').split('|') if u.strip()],
        )

    def _to_canonical(self, row: dict) -> CanonicalListing:
        for column in self.REQUIRED_COLUMNS:
            if not row.get(column):
                raise ValueError(f'{column} is required')

        price = _decimal(row['price'], 'price')
        if price <= 0:
            raise ValueError('price must be greater than zero')

        listing = CanonicalListing(
            source_listing_id=row['source_listing_id'],
            address_line=row['address_line'],
            city=row['city'],
            price=price,
            description=row.get('description', ''),
            state=row.get('state') or 'TX',
            zip_code=row.get('zip_code', ''),
            price_unit=row.get('price_unit') or 'mo',
            bedrooms=_int(row.get('bedrooms'), 'bedrooms'),
            bathrooms=_decimal(row.get('bathrooms'), 'bathrooms', required=False),
            square_footage=_int(row.get('square_footage'), 'square_footage'),
            year_built=_int(row.get('year_built'), 'year_built'),
            property_type=row.get('property_type', ''),
            accommodation_type=row.get('accommodation_type', ''),
            security_deposit=_decimal(row.get('security_deposit'), 'security_deposit', required=False),
            bills_included=row.get('bills_included', '').lower() in ('1', 'true', 'yes', 'y'),
            available_from=_date(row.get('available_from')),
            contact_phone=row.get('contact_phone', ''),
            virtual_tour_url=row.get('virtual_tour_url', ''),
            # The template uses '|' so tags survive a spreadsheet round-trip
            # unquoted; Listing.get_tags_list() splits on commas.
            tags=', '.join(t.strip() for t in row.get('tags', '').split('|') if t.strip()),
            photo_urls=[u.strip() for u in row.get('photo_urls', '').split('|') if u.strip()],
        )
        listing.title = row.get('title') or _default_title(listing)
        return listing


# ─────────────────────────────────────────────────────────────────────────────
# Import
# ─────────────────────────────────────────────────────────────────────────────

def import_partner_inventory(
    adapter: PartnerAdapter,
    *,
    organization: Organization,
    owner=None,
    status: str = 'active',
    limit: int = 0,
    dry_run: bool = False,
    fetch_photos: bool = True,
    deactivation_ceiling: float = DEFAULT_DEACTIVATION_CEILING,
) -> ImportResult:
    """
    Upsert an organization's inventory, then reconcile what the feed omitted.

    Standalone rows match on (organization, source_listing_id); communities
    resolve through `SourceRecordMap` so a property that changed managers is
    recognized rather than duplicated. Never matched on address.

    Anything the feed omits goes *pending* first and is only retired when a
    second run also omits it.
    """
    owner = owner or organization.owner_user
    result = ImportResult()
    seen_ids: set[str] = set()
    seen_units: set[tuple[str, str]] = set()
    records: list[CanonicalListing] = []
    unit_records: list[CanonicalUnit] = []

    for _row_number, record, rejection in adapter.iter_listings():
        if rejection:
            result.rejections.append(rejection)
            continue
        if limit and (len(records) + len(unit_records)) >= limit:
            break

        if isinstance(record, CanonicalUnit):
            key = (record.community_ref, record.source_unit_id)
            if key in seen_units:
                result.rejections.append(Rejection(
                    _row_number,
                    f'Duplicate unit "{record.source_unit_id}" for community '
                    f'"{record.community_ref}" in this file', {}))
                continue
            seen_units.add(key)
            unit_records.append(record)
            continue

        if record.source_listing_id in seen_ids:
            result.rejections.append(Rejection(
                _row_number, f'Duplicate source_listing_id "{record.source_listing_id}" in this file', {}))
            continue
        seen_ids.add(record.source_listing_id)
        records.append(record)

    if not records and not unit_records:
        result.aborted_reason = 'No valid rows found — nothing was changed'
        return result

    if owner is None:
        result.aborted_reason = (
            f'{organization.name} has no members — add one before importing, '
            f'so inventory has an account to attribute rows to')
        return result

    # Feed authority: a partner may only write to properties they currently
    # manage. Without this, a stale cron from the previous manager overwrites
    # the new one's pricing after a handover.
    unauthorized = _unauthorized_source_ids(organization, unit_records)
    if unauthorized:
        result.aborted_reason = (
            f'{organization.name} does not currently manage: {", ".join(sorted(unauthorized))}. '
            f'Transfer management before importing, or the previous manager still owns it.')
        return result

    partner_rows = Listing.objects.filter(organization=organization, source_type='partner_csv')
    partner_units = Unit.objects.filter(floor_plan__community__managed_by=organization)

    live_before = (partner_rows.exclude(status='closed').count()
                   + partner_units.exclude(status='withdrawn').count())
    missing_count = (
        partner_rows.exclude(status='closed').exclude(source_listing_id__in=seen_ids).count()
        + _absent_units(organization, seen_units).count())

    # Guard before writing anything: a truncated file looks exactly like a
    # partner who emptied their portfolio, and only one of those is likely.
    if not limit and live_before and missing_count / live_before > deactivation_ceiling:
        share = missing_count / live_before
        result.aborted_reason = (
            f'File omits {missing_count} of {live_before} live listings/units '
            f'({share:.0%}, ceiling {deactivation_ceiling:.0%}). '
            f'Looks like a partial upload — re-run with a higher ceiling to override.')
        return result

    if dry_run:
        existing = set(partner_rows.values_list('source_listing_id', flat=True))
        result.created = len([r for r in records if r.source_listing_id not in existing])
        result.updated = len(records) - result.created
        known = set(SourceRecordMap.objects.filter(organization=organization)
                    .values_list('source_id', flat=True))
        result.communities = len({r.community_ref for r in unit_records} - known)
        result.floor_plans = len({(r.community_ref, r.floor_plan_name) for r in unit_records})
        result.units = len(unit_records)
        result.pending_deactivation = missing_count
        return result

    with transaction.atomic():
        for record in records:
            _created, photos = _upsert(record, organization=organization, owner=owner,
                                       status=status, fetch_photos=fetch_photos)
            result.created += int(_created)
            result.updated += int(not _created)
            result.photos_saved += photos

        if unit_records:
            _import_units(unit_records, organization=organization, owner=owner,
                          fetch_photos=fetch_photos, result=result)

        pending, deactivated = _reconcile_absent(organization, seen_ids)
        unit_pending, unit_deactivated = _reconcile_absent_units(organization, seen_units)
        result.pending_deactivation = pending + unit_pending
        result.deactivated = deactivated + unit_deactivated

    return result


def _unauthorized_source_ids(organization: Organization,
                             unit_records: list[CanonicalUnit]) -> set[str]:
    """
    Source IDs in this file that map to communities someone else manages now.

    Only already-mapped properties can fail: an unmapped ID is a property this
    partner is introducing, which they are by definition entitled to do.
    """
    refs = {r.community_ref for r in unit_records}
    if not refs:
        return set()

    mapped = SourceRecordMap.objects.filter(
        organization=organization, source_id__in=refs).select_related('community')

    return {
        row.source_id for row in mapped
        if row.community.managed_by_id not in (None, organization.pk)
    }


def _resolve_community(source_id: str, record: CanonicalUnit, *,
                       organization: Organization, owner) -> tuple[Community, bool]:
    """
    Find the community this partner's ID refers to, or create it.

    Resolution goes through SourceRecordMap rather than a partner ID stored on
    Community. That indirection is the whole point: one building keeps one
    identity while each manager refers to it by their own PMS ID, so a change
    of manager updates the property instead of cloning it.
    """
    mapping = (SourceRecordMap.objects
               .filter(organization=organization, source_id=source_id)
               .select_related('community').first())
    if mapping:
        return mapping.community, False

    community = Community.objects.create(
        **record.community_fields(), owner=owner,
        managed_by=organization, status='active')
    SourceRecordMap.objects.create(
        organization=organization, source_id=source_id, community=community)
    ManagementAssignment.objects.create(
        community=community, organization=organization, note='Created from partner feed')
    return community, True


def _import_units(unit_records: list[CanonicalUnit], *, organization: Organization, owner,
                  fetch_photos: bool, result: ImportResult) -> None:
    """
    Build Community → FloorPlan → Unit from flat rows.

    Community and floor-plan attributes repeat on every unit row, so the last
    row of a group wins. That is intentional: a partner correcting an amenity
    list edits it on all rows, and re-importing should reflect the correction.
    """
    by_community: dict[str, list[CanonicalUnit]] = {}
    for record in unit_records:
        by_community.setdefault(record.community_ref, []).append(record)

    for community_ref, rows in by_community.items():
        community, created = _resolve_community(
            community_ref, rows[-1], organization=organization, owner=owner)

        if not created:
            for attr, value in rows[-1].community_fields().items():
                setattr(community, attr, value)
            community.save()

        # Counted in `communities`, not `created` — `created`/`updated` stay
        # about standalone listings so the two shapes never blur in the report.
        result.communities += int(created)

        if fetch_photos and rows[-1].photo_urls and not community.images.exists():
            result.photos_saved += _save_community_photos(community, rows[-1].photo_urls)

        for record in rows:
            floor_plan, fp_created = FloorPlan.objects.update_or_create(
                community=community,
                name=record.floor_plan_name,
                defaults=record.floor_plan_fields(),
            )
            result.floor_plans += int(fp_created)

            _unit, unit_created = Unit.objects.update_or_create(
                floor_plan__community=community,
                source_unit_id=record.source_unit_id,
                defaults={**record.unit_fields(), 'floor_plan': floor_plan},
            )
            result.units += int(unit_created)
            result.units_updated += int(not unit_created)


def _save_community_photos(community, photo_urls) -> int:
    from listings.services.media import save_remote_photos
    return save_remote_photos(community, photo_urls, image_model=CommunityImage,
                              related_field='community', prefix='community',
                              upload_dir='community_images')


def _absent_units(organization: Organization, seen_units: set[tuple[str, str]]):
    """
    Live units in this organization's portfolio that the file did not mention.

    Scoped by current management, so a property handed to another company drops
    out of reconciliation entirely rather than being retired by a stale feed.
    """
    absent = Unit.objects.filter(
        floor_plan__community__managed_by=organization,
    ).exclude(status='withdrawn')

    community_by_source = dict(
        SourceRecordMap.objects.filter(organization=organization)
        .values_list('source_id', 'community_id'))

    for community_ref, source_unit_id in seen_units:
        community_id = community_by_source.get(community_ref)
        if community_id is None:
            continue
        absent = absent.exclude(
            floor_plan__community_id=community_id,
            source_unit_id=source_unit_id,
        )
    return absent


def _reconcile_absent_units(organization: Organization,
                            seen_units: set[tuple[str, str]]) -> tuple[int, int]:
    """Two-strike deactivation for units. Absent twice → withdrawn."""
    absent = _absent_units(organization, seen_units)

    withdrawn = Unit.objects.filter(
        pk__in=list(absent.filter(deactivation_pending_since__isnull=False)
                    .values_list('pk', flat=True))
    ).update(status='withdrawn', deactivation_pending_since=None)

    pending = Unit.objects.filter(
        pk__in=list(absent.filter(deactivation_pending_since__isnull=True)
                    .values_list('pk', flat=True))
    ).update(deactivation_pending_since=timezone.now())

    return pending, withdrawn


def _upsert(record: CanonicalListing, *, organization: Organization, owner, status: str,
            fetch_photos: bool) -> tuple[bool, int]:
    defaults = record.as_listing_fields()
    defaults.update(owner=owner, status=status, category='rentals',
                    source_type='partner_csv', deactivation_pending_since=None)

    listing, created = Listing.objects.update_or_create(
        organization=organization,
        source_listing_id=record.source_listing_id,
        source_type='partner_csv',
        defaults=defaults,
    )

    photos = 0
    if fetch_photos and record.photo_urls and not listing.images.exists():
        from listings.services.media import save_remote_photos
        photos = save_remote_photos(listing, record.photo_urls)

    return created, photos


def _reconcile_absent(organization: Organization, seen_ids: set[str]) -> tuple[int, int]:
    """
    Two-strike deactivation (blueprint §13).

    First run that omits a listing marks it pending. A later run that also omits
    it closes it. A run that includes it again clears the mark — handled in
    `_upsert`, which resets `deactivation_pending_since` on every write.
    """
    absent = Listing.objects.filter(
        organization=organization, source_type='partner_csv',
    ).exclude(status='closed').exclude(source_listing_id__in=seen_ids)

    deactivated = absent.filter(deactivation_pending_since__isnull=False).update(
        status='closed', deactivation_pending_since=None)
    pending = absent.filter(deactivation_pending_since__isnull=True).update(
        deactivation_pending_since=timezone.now())

    return pending, deactivated


# ─────────────────────────────────────────────────────────────────────────────
# Parsing helpers — every failure names the column, because the message ends up
# in front of a property manager who did not write this file by hand.
# ─────────────────────────────────────────────────────────────────────────────

def _decimal(value, column: str, *, required: bool = True) -> Decimal | None:
    if value in (None, ''):
        if required:
            raise ValueError(f'{column} is required')
        return None
    try:
        return Decimal(str(value).replace(',', '').replace('$', ''))
    except (InvalidOperation, ValueError):
        raise ValueError(f'{column} "{value}" is not a number')


def _int(value, column: str) -> int | None:
    if value in (None, ''):
        return None
    try:
        return int(float(str(value).replace(',', '')))
    except (TypeError, ValueError):
        raise ValueError(f'{column} "{value}" is not a whole number')


def _date(value) -> date | None:
    if not value:
        return None
    for fmt in ('%Y-%m-%d', '%m/%d/%Y', '%m/%d/%y', '%d-%b-%Y'):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    raise ValueError(f'available_from "{value}" is not a recognized date (use YYYY-MM-DD)')


def _commas(value: str) -> str:
    """Pipe-separated in the template, comma-separated in the model."""
    return ', '.join(part.strip() for part in value.split('|') if part.strip())


def _default_title(listing: CanonicalListing) -> str:
    beds = f'{listing.bedrooms}BR ' if listing.bedrooms else ''
    kind = (listing.property_type or 'rental').replace('_', ' ').title()
    return f'{beds}{kind} in {listing.city}'.strip()
