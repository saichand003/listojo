"""
Local-only demo inventory for developing the Fit Report.

Creates a handful of DFW rentals with the neighbourhood data the Fit Report
reads (commute, groceries, schools, walkability, transit) plus renter view
events carrying preferences, so the renter cards, the landlord's listing
strength and the renter-demand insights can be seen with realistic data.

    python manage.py seed_fit_demo            # create (idempotent: replaces its own rows)
    python manage.py seed_fit_demo --clear    # remove what it created

It refuses to run outside DEBUG or on Railway. These are made-up homes: on a
live site renters would take them for real listings.
"""
import os
import random
from datetime import date, timedelta
from decimal import Decimal

from django.conf import settings
from django.contrib.auth.models import User
from django.core.management import BaseCommand, CommandError, call_command

from listings.models import (
    Downtown, GroceryStore, Listing, ListingGroceryStore, ListingImage, ListingSchool,
    ListingTransitStation, School, TransitAgency, TransitStation, UserListingEvent,
)

OWNER = 'fitdemo_landlord'
PREFIX = 'fitdemo'

# (title, city, zip, lat, lng, price, beds, sqft, tags, commute, label, downtown_min,
#  walk, grocery (chain, minutes), school (name, rating, miles), photos, available_in_days)
HOMES = [
    ('Lakeview 2BR at Las Colinas', 'Irving', '75039', 32.8870, -96.9420, 1725, 2, 1050,
     'pet-friendly, parking, gym, pool, washer/dryer', 78, 'Good Transit', 17, 62,
     ('Kroger', 4), ('Townley Elementary', 7, 0.8), 5, 0),
    ('Quiet 2BR Townhome off MacArthur', 'Irving', '75063', 32.9180, -96.9590, 1580, 2, 1180,
     'pet-friendly, parking, patio', 44, 'Some Transit', 24, 38,
     ('Tom Thumb', 9), ('Farine Elementary', 6, 1.1), 3, 14),
    ('Budget 2BR near DFW Airport', 'Irving', '75062', 32.8480, -96.9830, 1295, 2, 890,
     'parking', 31, 'Minimal Transit', 29, 27,
     ('Walmart', 14), ('Lively Elementary', 4, 1.6), 0, 30),
    ('Uptown 1BR with Skyline View', 'Dallas', '75204', 32.8000, -96.8010, 1890, 1, 760,
     'pet-friendly, gym, pool, balcony, washer/dryer', 91, 'Excellent Transit', 6, 88,
     ('Whole Foods', 3), ('Ben Milam Elementary', 5, 0.6), 6, 0),
    ('Bishop Arts 2BR Bungalow', 'Dallas', '75208', 32.7490, -96.8280, 1650, 2, 980,
     'pet-friendly, washer/dryer, backyard', 63, 'Good Transit', 12, 71,
     ('Fiesta', 5), ('Rosemont Elementary', 6, 0.5), 4, 7),
    ('Legacy West 2BR Loft', 'Plano', '75024', 33.0770, -96.8280, 2150, 2, 1120,
     'pet-friendly, parking, gym, pool, washer/dryer, EV charging', 52, 'Some Transit', 31, 55,
     ('H-E-B', 6), ('Hughston Elementary', 9, 0.9), 8, 0),
    ('Spacious 3BR near Plano Schools', 'Plano', '75093', 33.0290, -96.8330, 2350, 3, 1460,
     'parking, backyard, washer/dryer', 38, 'Some Transit', 33, 32,
     ('Kroger', 7), ('Haggard Elementary', 9, 0.4), 5, 21),
]

# What renters who viewed the listings were looking for (drives renter-demand insights).
RENTER_WANTS = [
    {'max_price': '1800', 'bedrooms': '2', 'tags': 'pet-friendly,washer/dryer'},
    {'max_price': '1700', 'bedrooms': '2', 'tags': 'washer/dryer,parking'},
    {'max_price': '2000', 'bedrooms': '2', 'tags': 'pool,gym'},
    {'max_price': '1600', 'bedrooms': '2', 'tags': 'washer/dryer'},
    {'max_price': '1900', 'bedrooms': '2', 'tags': 'pet-friendly'},
    {'max_price': '1500', 'bedrooms': '2', 'tags': 'washer/dryer,pet-friendly'},
    {'max_price': '2200', 'bedrooms': '2', 'tags': 'gym,washer/dryer'},
    {'max_price': '1750', 'bedrooms': '2', 'tags': 'parking'},
    {'max_price': '1650', 'bedrooms': '2', 'tags': 'washer/dryer,balcony'},
    {'max_price': '1800', 'bedrooms': '2', 'tags': 'pet-friendly,washer/dryer'},
    {'max_price': '1550', 'bedrooms': '2', 'tags': 'washer/dryer'},
    {'max_price': '2000', 'bedrooms': '2', 'tags': 'pet-friendly,pool'},
]


class Command(BaseCommand):
    help = 'Create local-only demo listings with neighbourhood data for the Fit Report.'

    def add_arguments(self, parser):
        parser.add_argument('--clear', action='store_true', help='Remove the demo rows and stop.')

    def handle(self, *args, clear=False, **opts):
        if not settings.DEBUG or os.getenv('RAILWAY_ENVIRONMENT') or os.getenv('RAILWAY_PROJECT_ID'):
            raise CommandError('seed_fit_demo is local-only: it creates made-up homes that renters '
                               'would take for real listings.')

        self._clear()
        if clear:
            self.stdout.write('Removed Fit Report demo data.')
            return

        if not Downtown.objects.exists():
            call_command('seed_downtowns', verbosity=0)
        dallas = Downtown.objects.filter(name__icontains='Dallas').first() or Downtown.objects.first()

        owner, _ = User.objects.get_or_create(username=OWNER, defaults={'email': 'fitdemo@example.com'})
        owner.set_password('fitdemo')
        owner.save()

        agency, _ = TransitAgency.objects.get_or_create(
            slug=f'{PREFIX}-dart', defaults={'name': 'DART (demo)', 'gtfs_url': 'https://example.com/gtfs.zip'})
        photos = sorted(p.name for p in (settings.MEDIA_ROOT / 'listing_images').glob('demo_*'))

        rows = []
        for (title, city, zip_code, lat, lng, price, beds, sqft, tags, commute, label, dt_min,
             walk, *_rest) in HOMES:
            rows.append(Listing(
                owner=owner, title=title, city=city, state='TX', zip_code=zip_code,
                description=f'{title}. Local demo data for the Fit Report.',
                category='rentals', accommodation_type='whole', property_type='apartment',
                price=Decimal(price), price_unit='mo', bedrooms=beds, square_footage=sqft,
                tags=tags, status='active', latitude=Decimal(str(lat)), longitude=Decimal(str(lng)),
                commute_score=commute, commute_score_label=label,
                nearest_downtown=dallas, downtown_drive_minutes=dt_min,
                walk_score=walk,
                walk_score_description='Walker\'s Paradise' if walk >= 90 else 'Very Walkable' if walk >= 70
                else 'Somewhat Walkable' if walk >= 50 else 'Car-Dependent',
            ))
        # bulk_create skips the pre_save geocoding signal: no paid API calls for demo rows.
        created = Listing.objects.bulk_create(rows)

        for listing, home in zip(created, HOMES):
            (grocery, minutes), (school, rating, miles), n_photos, avail = home[13], home[14], home[15], home[16]
            store, _ = GroceryStore.objects.get_or_create(
                place_id=f'{PREFIX}-{grocery}-{listing.zip_code}', defaults={'chain': grocery, 'name': grocery})
            ListingGroceryStore.objects.create(listing=listing, store=store, drive_minutes=minutes,
                                               distance_miles=Decimal(str(round(minutes * 0.45, 1))))
            sch, _ = School.objects.get_or_create(
                gs_id=f'{PREFIX}-{school}', defaults={'name': school, 'rating': rating, 'city': listing.city})
            ListingSchool.objects.create(listing=listing, school=sch, distance_miles=Decimal(str(miles)))
            if listing.commute_score >= 60:
                station = TransitStation.objects.create(
                    agency=agency, source_id=f'{PREFIX}-{listing.pk}', name=f'{listing.city} Station',
                    latitude=listing.latitude, longitude=listing.longitude, mode='light_rail', is_rail=True)
                ListingTransitStation.objects.create(listing=listing, station=station,
                                                     distance_miles=Decimal('0.4'))
            for i in range(min(n_photos, len(photos))):
                ListingImage.objects.create(listing=listing, image=f'listing_images/{photos[i % len(photos)]}',
                                            order=i)
            if avail:
                Listing.objects.filter(pk=listing.pk).update(available_from=date.today() + timedelta(days=avail))

        # Renter views with the preferences they had at the time.
        rng = random.Random(7)
        for listing in created:
            for i, wants in enumerate(RENTER_WANTS):
                if rng.random() < 0.85:
                    UserListingEvent.objects.create(
                        session_key=f'{PREFIX}-s{listing.pk}-{i}', listing=listing, event_type='click',
                        user_features_snapshot=wants)
            Listing.objects.filter(pk=listing.pk).update(view_count=len(RENTER_WANTS) + rng.randint(5, 40))

        self.stdout.write(self.style.SUCCESS(
            f'Created {len(created)} demo listings for "{OWNER}" (password: fitdemo).'))

    def _clear(self):
        Listing.objects.filter(owner__username=OWNER).delete()
        TransitStation.objects.filter(source_id__startswith=PREFIX).delete()
        TransitAgency.objects.filter(slug__startswith=PREFIX).delete()
        GroceryStore.objects.filter(place_id__startswith=PREFIX).delete()
        School.objects.filter(gs_id__startswith=PREFIX).delete()
        UserListingEvent.objects.filter(session_key__startswith=PREFIX).delete()
