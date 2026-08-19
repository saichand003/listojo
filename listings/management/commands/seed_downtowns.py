"""
Seed the Downtown table with the metros Listojo currently covers.

    python manage.py seed_downtowns
    python manage.py seed_downtowns --update   # also refresh existing rows

Coordinates are hand-placed on each city's centre and are approximate by
nature: "downtown" is a district, not a point, and a tenth of a mile either way
does not change how the distance reads. Refine any of them in admin rather than
editing this file if the change is local to one deployment.

Safe to re-run — rows are matched on name and left alone unless --update.
"""
from django.core.management.base import BaseCommand

from listings.models import Downtown

# (name, city, state, lat, lng) — Texas metros first, since that is where the
# supply pipeline is. Add rows as the site enters new markets.
DOWNTOWNS = [
    ('Downtown Dallas',        'Dallas',       'TX', 32.7767, -96.7970),
    ('Downtown Fort Worth',    'Fort Worth',   'TX', 32.7555, -97.3308),
    ('Downtown Las Colinas',    'Irving',       'TX', 32.8626, -96.9433),
    ('Downtown Plano',         'Plano',        'TX', 33.0198, -96.6989),
    ('Downtown Frisco',        'Frisco',       'TX', 33.1507, -96.8236),
    ('Downtown Arlington',     'Arlington',    'TX', 32.7357, -97.1081),
    ('Downtown Denton',        'Denton',       'TX', 33.2148, -97.1331),
    ('Downtown McKinney',      'McKinney',     'TX', 33.1972, -96.6153),
    ('Downtown Grapevine',     'Grapevine',    'TX', 32.9343, -97.0781),
    ('Keller Town Center',     'Keller',       'TX', 32.9346, -97.2289),
    ('Downtown Garland',       'Garland',      'TX', 32.9126, -96.6389),
    ('Downtown Richardson',    'Richardson',   'TX', 32.9483, -96.7299),
    ('Downtown Austin',        'Austin',       'TX', 30.2672, -97.7431),
    ('Downtown Houston',       'Houston',      'TX', 29.7604, -95.3698),
    ('Downtown San Antonio',   'San Antonio',  'TX', 29.4241, -98.4936),
]


class Command(BaseCommand):
    help = 'Create the curated Downtown rows used for nearest-downtown matching.'

    def add_arguments(self, parser):
        parser.add_argument('--update', action='store_true',
                            help='Overwrite coordinates on rows that already exist.')

    def handle(self, *args, **opts):
        created = updated = skipped = 0

        for name, city, state, lat, lng in DOWNTOWNS:
            defaults = {'city': city, 'state': state,
                        'latitude': lat, 'longitude': lng, 'is_active': True}

            if opts['update']:
                _, was_created = Downtown.objects.update_or_create(name=name, defaults=defaults)
                created += was_created
                updated += not was_created
            else:
                _, was_created = Downtown.objects.get_or_create(name=name, defaults=defaults)
                created += was_created
                skipped += not was_created

        self.stdout.write(self.style.SUCCESS(
            f'Downtowns: {created} created, {updated} updated, {skipped} left alone.'))
