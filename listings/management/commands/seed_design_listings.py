"""
Seed the 12 sample listings shown in the Listojo Claude design prototype
(6 rentals/roommates + 6 properties for sale).
Run with:  python manage.py seed_design_listings
"""
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta
import random

User = get_user_model()

LISTINGS = [
    {
        "title": "Modern 2BR Apartment — Las Colinas",
        "description": (
            "Beautiful modern 2-bedroom apartment in the heart of Las Colinas. "
            "Open floor plan, updated kitchen with stainless appliances, in-unit washer/dryer. "
            "Walking distance to Las Colinas Urban Center and Water Street shops. "
            "Pet-friendly building with gym and covered parking."
        ),
        "price": 1650,
        "price_unit": "mo",
        "category": "rentals",
        "property_type": "apartment",
        "bedrooms": 2,
        "city": "Irving",
        "state": "TX",
        "tags": "parking, pet-friendly, gym",
        "featured": True,
        "hours_ago": 2,
    },
    {
        "title": "Cozy Studio Near DFW Airport",
        "description": (
            "Fully furnished studio apartment, perfect for travelers, remote workers, or short-term stays. "
            "5 minutes from DFW Airport. High-speed WiFi, smart TV, fully equipped kitchen. "
            "No deposit required. All utilities included. Near DART transit stop."
        ),
        "price": 950,
        "price_unit": "mo",
        "category": "rentals",
        "property_type": "studio",
        "bedrooms": 0,
        "city": "Irving",
        "state": "TX",
        "tags": "furnished, no deposit, near transit",
        "featured": False,
        "hours_ago": 5,
    },
    {
        "title": "Spacious 3BR House with Backyard",
        "description": (
            "Large 3-bedroom, 2-bath house with a private backyard perfect for families or roommates. "
            "New flooring throughout, updated bathrooms, two-car garage. "
            "Quiet neighborhood, great schools nearby. Pool in the community. Pet-friendly."
        ),
        "price": 2100,
        "price_unit": "mo",
        "category": "rentals",
        "property_type": "house",
        "bedrooms": 3,
        "city": "Irving",
        "state": "TX",
        "tags": "pet-friendly, pool, parking",
        "featured": False,
        "hours_ago": 26,
    },
    {
        "title": "1BR Condo — Las Colinas Waterway",
        "description": (
            "Stunning 1-bedroom condo overlooking the Las Colinas Waterway. "
            "Floor-to-ceiling windows, granite countertops, resort-style amenities. "
            "Access to rooftop gym, balcony with water views, utilities included. "
            "Minutes from Toyota Music Factory and Las Colinas dining."
        ),
        "price": 1300,
        "price_unit": "mo",
        "category": "rentals",
        "property_type": "condo",
        "bedrooms": 1,
        "city": "Irving",
        "state": "TX",
        "tags": "utilities included, gym, balcony",
        "featured": False,
        "hours_ago": 3,
    },
    {
        "title": "Townhouse 2BR — Quiet Neighborhood",
        "description": (
            "Well-maintained 2-bedroom townhouse in a peaceful, gated community. "
            "Private patio, in-unit washer/dryer, attached garage. "
            "Great for families or professionals. Close to schools, parks, and shopping. "
            "Gated entrance for added security."
        ),
        "price": 1800,
        "price_unit": "mo",
        "category": "rentals",
        "property_type": "townhouse",
        "bedrooms": 2,
        "city": "Irving",
        "state": "TX",
        "tags": "washer/dryer, parking, gated",
        "featured": False,
        "hours_ago": 6,
    },
    {
        "title": "Private Room in Shared House",
        "description": (
            "Furnished private room in a clean, friendly shared house. "
            "All bills included — electricity, water, WiFi. Shared kitchen and living room. "
            "Quiet housemates, great for students or young professionals. "
            "Near transit, easy access to DFW metro area."
        ),
        "price": 680,
        "price_unit": "mo",
        "category": "roommates",
        "property_type": "room",
        "bedrooms": 1,
        "city": "Irving",
        "state": "TX",
        "tags": "furnished, bills included, near transit",
        "featured": False,
        "hours_ago": 12,
    },

    # ── Properties for Sale (Buy tab) ──────────────────────────────
    {
        "title": "4BR Single-Family Home — MacArthur",
        "description": (
            "Beautiful 4-bedroom, 3-bath single-family home in the sought-after MacArthur area. "
            "Renovated kitchen with granite countertops, hardwood floors throughout. "
            "Large backyard with mature trees, 2-car garage. Top-rated schools nearby. "
            "Close to major highways, shopping, and dining."
        ),
        "price": 389000,
        "price_unit": "",
        "category": "properties",
        "property_type": "single_family",
        "bedrooms": 4,
        "city": "Irving",
        "state": "TX",
        "tags": "2-car garage, backyard, schools",
        "featured": True,
        "hours_ago": 28,
    },
    {
        "title": "3BR Ranch House on 1 Acre",
        "description": (
            "Charming 3-bedroom ranch-style home sitting on a full acre of land in Mansfield. "
            "Original hardwood floors, updated bathrooms, wood-burning fireplace. "
            "Detached barn, fenced property, peaceful and quiet surroundings. "
            "Perfect for those wanting space and privacy outside the city."
        ),
        "price": 475000,
        "price_unit": "",
        "category": "properties",
        "property_type": "ranch_house",
        "bedrooms": 3,
        "city": "Mansfield",
        "state": "TX",
        "tags": "land, barn, quiet",
        "featured": False,
        "hours_ago": 4,
    },
    {
        "title": "Modern Condo — Downtown Irving",
        "description": (
            "Sleek modern condo in the heart of Downtown Irving. "
            "Floor-to-ceiling windows with stunning city views, open-concept living, "
            "chef's kitchen with quartz countertops. Building amenities include "
            "rooftop gym, concierge service, and secure parking. Walk to restaurants and entertainment."
        ),
        "price": 290000,
        "price_unit": "",
        "category": "properties",
        "property_type": "condo",
        "bedrooms": 2,
        "city": "Irving",
        "state": "TX",
        "tags": "gym, concierge, city views",
        "featured": False,
        "hours_ago": 8,
    },
    {
        "title": "2BR Townhouse — Las Colinas",
        "description": (
            "Well-maintained 2-bedroom townhouse in a premier Las Colinas community. "
            "Updated kitchen, private patio, attached garage. "
            "HOA covers exterior maintenance, landscaping, and community amenities. "
            "Highly walkable — steps from Water Street shops, restaurants, and the waterway trail."
        ),
        "price": 335000,
        "price_unit": "",
        "category": "properties",
        "property_type": "townhouse",
        "bedrooms": 2,
        "city": "Irving",
        "state": "TX",
        "tags": "HOA, parking, walkable",
        "featured": False,
        "hours_ago": 50,
    },
    {
        "title": "Land Plot 0.5 Acre — North Irving",
        "description": (
            "Rare 0.5-acre vacant land parcel in North Irving. "
            "Flat, cleared lot — ready to build your dream home. "
            "No HOA restrictions. Utilities available at street. "
            "Centrally located with easy access to DFW Airport, highways, and shopping."
        ),
        "price": 125000,
        "price_unit": "",
        "category": "properties",
        "property_type": "land",
        "bedrooms": None,
        "city": "Irving",
        "state": "TX",
        "tags": "land, no HOA",
        "featured": False,
        "hours_ago": 72,
    },
    {
        "title": "5BR Luxury Home — Coppell",
        "description": (
            "Stunning brand-new 5-bedroom luxury home in the prestigious Coppell school district. "
            "3-car garage, resort-style pool and spa, gourmet kitchen with high-end appliances. "
            "Open floor plan, vaulted ceilings, premium finishes throughout. "
            "New build — never lived in. Golf course community."
        ),
        "price": 750000,
        "price_unit": "",
        "category": "properties",
        "property_type": "single_family",
        "bedrooms": 5,
        "city": "Coppell",
        "state": "TX",
        "tags": "pool, 3-car garage, new build",
        "featured": False,
        "hours_ago": 5,
    },
]


class Command(BaseCommand):
    help = "Seed the 12 sample listings from the Listojo design prototype (6 rentals + 6 properties for sale)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Delete existing seed listings before creating new ones",
        )

    def handle(self, *args, **options):
        # Get or create a demo owner account
        owner, created = User.objects.get_or_create(
            username="listojo_demo",
            defaults={
                "email": "demo@listojo.com",
                "first_name": "Listojo",
                "last_name": "Demo",
            },
        )
        if created:
            owner.set_password("listojo2026!")
            owner.save()
            self.stdout.write(f"  Created demo user: listojo_demo / listojo2026!")

        if options["clear"]:
            from listings.models import Listing
            deleted, _ = Listing.objects.filter(owner=owner).delete()
            self.stdout.write(f"  Deleted {deleted} existing seed listings")

        from listings.models import Listing

        now = timezone.now()
        created_count = 0

        for data in LISTINGS:
            hours_ago = data.pop("hours_ago")
            created_at = now - timedelta(hours=hours_ago)

            listing, new = Listing.objects.get_or_create(
                owner=owner,
                title=data["title"],
                defaults={
                    **{k: v for k, v in data.items()},
                    "status": "active",
                    "country": "USA",
                    "description": data["description"],
                },
            )

            if new:
                # Manually set created_at (auto_now_add prevents direct assignment)
                Listing.objects.filter(pk=listing.pk).update(created_at=created_at)
                created_count += 1
                self.stdout.write(f"  ✓ Created: {listing.title}")
            else:
                self.stdout.write(f"  — Already exists: {listing.title}")

        self.stdout.write(
            self.style.SUCCESS(
                f"\nDone. {created_count} new listings created, "
                f"{len(LISTINGS) - created_count} already existed."
            )
        )
