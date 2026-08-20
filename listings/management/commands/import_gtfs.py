"""
Import transit routes and stations from agency GTFS feeds.

    python manage.py import_gtfs                 # every active agency
    python manage.py import_gtfs --agency dart   # just one
    python manage.py import_gtfs --seed          # create the default agency rows
    python manage.py import_gtfs --dry-run

Run `--seed` once to create the TransitAgency rows, then this on a schedule.
Agencies republish their feed every few weeks — the station list barely moves,
but route colours, names and frequencies do, so quarterly is ample.

No API key and no per-listing cost: these are static zips published under an
open licence. That is the whole reason the transit card and the Commute Score
can be shown on every listing without spend scaling with volume.

After importing, run `fetch_transit` to re-match listings against the new
station table.
"""
from django.core.cache import cache
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from listings.models import (StationRoute, TransitAgency, TransitRoute,
                             TransitStation)
from listings.services.gtfs import FREQUENT_TRIPS_PER_WEEKDAY, load_feed
from listings.services.transit import _IMPORT_STAMP_KEY

# Seeded by --seed. URLs verified reachable 2026-08-20; they live in the
# database, so a moved feed is an admin edit rather than a deploy.
#
# Only agencies whose feed URL was actually confirmed are listed. Houston METRO,
# VIA (San Antonio), Trinity Metro and DCTA all publish GTFS but none of their
# documented URLs resolved when this was written — add them here, or via admin,
# once a working link is confirmed. DART's feed already carries the TRE, which
# is what puts Fort Worth's T&P and Central stations on the map today.
DEFAULT_AGENCIES = [
    ('dart',      'DART',      'Dallas Area Rapid Transit',
     'https://www.dart.org/transitdata/latest/google_transit.zip'),
    ('capmetro',  'CapMetro',  'Capital Metro (Austin)',
     'https://data.texas.gov/download/r4v4-vz24/application%2Fzip'),
]


class Command(BaseCommand):
    help = 'Import transit routes and stations from agency GTFS feeds.'

    def add_arguments(self, parser):
        parser.add_argument('--agency', default='',
                            help='Import only this agency slug.')
        parser.add_argument('--seed', action='store_true',
                            help='Create the default TransitAgency rows, then exit.')
        parser.add_argument('--dry-run', action='store_true',
                            help='Report what would be imported without saving.')

    def handle(self, *args, **opts):
        if opts['seed']:
            return self._seed()

        qs = TransitAgency.objects.filter(is_active=True)
        if opts['agency']:
            qs = qs.filter(slug=opts['agency'])

        agencies = list(qs)
        if not agencies:
            self.stdout.write(self.style.WARNING(
                'No active agencies. Run with --seed first.'))
            return

        for agency in agencies:
            self._import_one(agency, dry=opts['dry_run'])

    def _seed(self):
        created = 0
        for slug, name, full_name, url in DEFAULT_AGENCIES:
            _, was_created = TransitAgency.objects.get_or_create(
                slug=slug,
                defaults={'name': name, 'full_name': full_name, 'gtfs_url': url},
            )
            created += was_created
            self.stdout.write(f'  {"+" if was_created else "·"} {name}')
        self.stdout.write(self.style.SUCCESS(
            f'\nSeeded {created} new agency row(s). Now run: manage.py import_gtfs'))

    def _import_one(self, agency, *, dry: bool):
        self.stdout.write(f'\n{agency.name} — {agency.gtfs_url}')

        feed = load_feed(agency.gtfs_url)
        if feed is None:
            # Deliberately leaves the existing rows alone: a feed that 404s for
            # a day must not empty every listing's transit card.
            self.stdout.write(self.style.WARNING(
                '  ✗ feed unavailable or unreadable — existing rows left alone'))
            return

        rail = sum(1 for s in feed.stations if s.is_rail)
        frequent = sum(1 for s in feed.stations
                       if not s.is_rail and s.trips_per_weekday >= FREQUENT_TRIPS_PER_WEEKDAY)
        surface = len(feed.stations) - rail
        self.stdout.write(
            f'  {len(feed.routes)} route(s), {len(feed.stations)} station(s) '
            f'({rail} rail, {surface} surface — {frequent} of them frequent)')

        if dry:
            for station in sorted(feed.stations, key=lambda s: (not s.is_rail, s.name))[:15]:
                self.stdout.write(f'    [dry] {station.name} ({station.mode})')
            return

        with transaction.atomic():
            routes = {}
            for record in feed.routes:
                route, _ = TransitRoute.objects.update_or_create(
                    agency=agency, source_id=record.source_id,
                    defaults={
                        'short_name': record.short_name,
                        'long_name': record.long_name,
                        'mode': record.mode,
                        'color': record.color,
                        'text_color': record.text_color,
                        'trips_per_weekday': record.trips_per_weekday,
                        'is_frequent': record.is_frequent,
                    },
                )
                routes[record.source_id] = route

            seen_stations = set()
            for record in feed.stations:
                station, _ = TransitStation.objects.update_or_create(
                    agency=agency, source_id=record.source_id,
                    defaults={
                        'name': record.name,
                        'latitude': round(record.latitude, 6),
                        'longitude': round(record.longitude, 6),
                        'mode': record.mode,
                        'is_rail': record.is_rail,
                        'trips_per_weekday': record.trips_per_weekday,
                    },
                )
                seen_stations.add(station.pk)

                wanted = {routes[rid].pk for rid in record.route_ids if rid in routes}
                station.route_links.exclude(route_id__in=wanted).delete()
                existing = set(station.route_links.values_list('route_id', flat=True))
                StationRoute.objects.bulk_create(
                    [StationRoute(station=station, route_id=rid)
                     for rid in wanted - existing])

            # Rows the feed no longer publishes — a closed stop, or one that
            # dropped below the frequency threshold. Deleting cascades to the
            # listing links, which is correct: a listing must not keep claiming
            # a station that no longer exists.
            dropped, _ = (TransitStation.objects.filter(agency=agency)
                          .exclude(pk__in=seen_stations).delete())
            orphaned, _ = (TransitRoute.objects.filter(agency=agency, stations__isnull=True)
                           .delete())

            agency.last_imported = timezone.now()
            agency.feed_version = feed.feed_version
            if feed.agency_name and not agency.full_name:
                agency.full_name = feed.agency_name[:160]
            agency.save(update_fields=['last_imported', 'feed_version', 'full_name'])

        # Drop the memoised import stamp so a fetch_transit run started in the
        # same minute sees this import rather than the cached older one.
        cache.delete(_IMPORT_STAMP_KEY)

        self.stdout.write(self.style.SUCCESS(
            f'  ✓ imported (feed {feed.feed_version or "unversioned"}); '
            f'removed {dropped} stale station row(s), {orphaned} orphaned route row(s)'))
