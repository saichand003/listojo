import re

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.functional import cached_property


class ProximityDisplayMixin:
    """
    Read-only display helpers for anything with proximity data.

    Listing and Community carry the same proximity columns on separate tables —
    a building and a single rental are both a point on a map with a walk score,
    a nearest downtown and stations around it. The columns have to be duplicated
    because the tables are; this logic does not, and duplicating it is how the
    two pages drift apart.

    Every method here is a bare `.all()` or a Python filter over one, so a
    caller's `prefetch_related` is reused rather than re-queried per row.
    """

    @property
    def walk_score_rows(self):
        """
        (label, score, description) for each Walk Score metric that has data.

        Transit Score is deliberately absent: `commute_score` is shown in its
        place, and two transit numbers side by side invite a comparison neither
        one wins. The column is still populated by services.walkscore — it is
        licensed data we already fetch, and dropping the fetch would make it
        expensive to bring back.

        Bike coverage is patchy outside dense metros, so a row with no score is
        dropped here rather than guarded for in the template.
        """
        rows = [
            ('Walk Score', self.walk_score, self.walk_score_description),
            ('Bike Score', self.bike_score, self.bike_description),
        ]
        return [r for r in rows if r[1] is not None]

    @property
    def has_walk_scores(self):
        """True when at least one Walk Score metric is available to display."""
        return bool(self.walk_score_rows)

    @property
    def grocery_cards(self):
        """
        Nearby grocery stores for display, nearest first.

        A bare `.all()` for the same reason as `school_cards`: it is the only
        form that reuses a prefetch on the caller's queryset.
        """
        return self.nearby_groceries.all()

    @property
    def transit_cards(self):
        """
        Every nearby station, rail first then nearest.

        A bare `.all()` for the same reason as `school_cards`: it is the only
        form that reuses a prefetch on the caller's queryset. Ordering comes
        from ListingTransitStation.Meta, not from a call here.
        """
        return self.nearby_transit.all()

    @property
    def rail_cards(self):
        """
        Rail stations only, for the card's first section.

        Split in Python rather than with a `.filter()` so the caller's
        prefetch is reused — a filter here re-queries once per listing on any
        page showing more than one.
        """
        return [link for link in self.transit_cards if link.station.is_rail]

    @property
    def bus_cards(self):
        """Surface stops only — the card's second section. See `rail_cards`."""
        return [link for link in self.transit_cards if not link.station.is_rail]

    @property
    def transit_agencies(self):
        """
        Distinct agency names behind the stations on show, for attribution.

        GTFS feeds are published under licences that ask to be credited, and the
        card has no other place that names who the data came from. Reads the
        prefetched links rather than querying, so it costs nothing extra.
        """
        seen = []
        for link in self.transit_cards:
            name = link.station.agency.name
            if name not in seen:
                seen.append(name)
        return seen

    @property
    def has_commute_score(self):
        """True when a Commute Score has been computed for this listing."""
        return self.commute_score is not None

    @property
    def commute_score_tone(self):
        """
        Palette band for the score dial: 'strong', 'fair' or 'weak'.

        Named by band rather than by colour so the template picks the hex and
        this stays a data question. Thresholds match the Walk Score card's
        existing 70 / 50 split, so the two dials on the page read alike.
        """
        if self.commute_score is None:
            return 'weak'
        if self.commute_score >= 70:
            return 'strong'
        if self.commute_score >= 50:
            return 'fair'
        return 'weak'

    @property
    def downtown_display_miles(self):
        """Road miles when a route resolved, else the straight-line figure."""
        return self.downtown_drive_miles or self.downtown_distance_miles

    @property
    def has_drive_times(self):
        """True when any drive time is available — drives the card's footnote."""
        if self.downtown_drive_minutes:
            return True
        if any(link.drive_minutes for link in self.grocery_cards):
            return True
        return any(link.drive_minutes for link in self.transit_cards)

    @property
    def has_neighborhood_card(self):
        """True when there is anything to put in the Neighborhood section."""
        return bool(self.nearest_downtown_id) or bool(self.grocery_cards)


class AmenityDisplayMixin:
    """
    Read-only display helpers for the two amenity catalogues.

    The split is shared-versus-private, not indoor-versus-outdoor: the first
    card holds anything a resident shares with other residents or reaches
    outside their own front door, the second holds what is behind that door and
    theirs alone. That is the question a renter is actually asking — will I have
    to book, queue for or share this? — so the same word can land in either
    card: a laundry room is shared, a stacked unit in the closet is not.

    The labels are conditional because `Listing` spans more than apartments.
    "Community Amenities" is right for a complex and wrong for a single-family
    house, where a pool is the owner's, so the label follows the property type.
    `Community` is always a complex and always uses the community wording.
    """

    #: Property types where residents share facilities with other residents.
    #: Everything else — house, single_family, ranch, basement, trailer, land —
    #: has no community to speak of, so its first card is about the property.
    SHARED_FACILITY_PROPERTY_TYPES = frozenset({
        'apartment', 'condo', 'loft', 'studio', 'townhouse',
    })

    #: Free-text `tags` predates the two catalogues, so most listings still
    #: carry their amenities there and nowhere else. Those tags are folded into
    #: whichever card they belong to rather than shown as a loose chip row, so
    #: every detail page reads the same way. The split follows the same
    #: shared-versus-private question the cards ask; anything unrecognised
    #: falls to the shared card, whose heading describes the property as a
    #: whole and so still reads correctly for a stray descriptor.
    #:
    #: Short words are matched whole, not as substrings: "ac" is inside
    #: "backyard" and "package lockers", both of which are shared.
    PRIVATE_TAG_EXACT = frozenset({
        'ac', 'a/c', 'heat', 'heating', 'furnished', 'unfurnished', 'balcony',
        'patio', 'terrace', 'wifi', 'wi-fi', 'internet', 'cable', 'tile',
        'carpet', 'storage', 'closet', 'fireplace', 'dishwasher', 'oven',
        'stove', 'microwave', 'fridge', 'refrigerator', 'freezer', 'view',
        'renovated', 'updated',
    })

    #: Longer, unambiguous phrases — matched anywhere in the tag, so "in-unit
    #: washer/dryer" lands privately just like "washer/dryer".
    PRIVATE_TAG_KEYWORDS = (
        'washer', 'dryer', 'laundry in unit', 'in-unit laundry',
        'air conditioning', 'central air', 'hardwood', 'granite', 'quartz',
        'countertop', 'stainless', 'appliance', 'garbage disposal',
        'walk-in', 'ceiling fan', 'high ceiling', 'private bath', 'ensuite',
        'en-suite', 'natural light', 'updated kitchen', 'private entrance',
    )

    #: Acronyms and stylings a plain capitalisation would mangle. Tags are
    #: typed lowercase; the catalogue columns are typed in title case, and the
    #: two sit in the same card, so folded tags are cased to match.
    TAG_DISPLAY_OVERRIDES = {
        'ac': 'AC', 'a': 'A', 'c': 'C', 'hvac': 'HVAC', 'tv': 'TV', 'ev': 'EV',
        'wifi': 'WiFi', 'fi': 'Fi', 'hoa': 'HOA', 'bbq': 'BBQ',
    }

    def get_amenities_list(self, field):
        val = getattr(self, field, '') or ''
        return [a.strip() for a in val.split(',') if a.strip()]

    @classmethod
    def _display_tag(cls, tag):
        """Title-case a tag across word, slash and hyphen boundaries."""
        def cap(match):
            word = match.group(0)
            override = cls.TAG_DISPLAY_OVERRIDES.get(word.lower())
            if override:
                return override
            # A word the owner already capitalised is left as they typed it.
            return word if word != word.lower() else word.capitalize()

        return re.sub(r'[A-Za-z]+', cap, tag)

    @classmethod
    def _tag_is_private(cls, tag):
        low = tag.strip().lower()
        if low in cls.PRIVATE_TAG_EXACT:
            return True
        return any(k in low for k in cls.PRIVATE_TAG_KEYWORDS)

    def _tags_for_card(self, private):
        """
        The legacy `tags` that belong in one of the two cards.

        `private` picks the side: True for what is behind the tenant's own
        door, False for everything else. A tag already spelled out in either
        catalogue column is dropped, so an owner who filled in the new fields
        does not see the same amenity twice.
        """
        get_tags = getattr(self, 'get_tags_list', None)
        if not callable(get_tags):
            return []
        already = {
            a.strip().lower()
            for a in self.get_amenities_list('community_amenities')
                   + self.get_amenities_list('in_unit_amenities')
        }
        return [
            self._display_tag(t) for t in get_tags()
            if t.strip().lower() not in already and self._tag_is_private(t) == private
        ]

    @property
    def community_amenities_list(self):
        return self.get_amenities_list('community_amenities') + self._tags_for_card(private=False)

    @property
    def in_unit_amenities_list(self):
        return self.get_amenities_list('in_unit_amenities') + self._tags_for_card(private=True)

    @property
    def shared_amenities_label(self):
        """Heading for the shared card — 'Community Amenities' or 'Property Features'."""
        if getattr(self, 'property_type', None) in self.SHARED_FACILITY_PROPERTY_TYPES:
            return 'Community Amenities'
        return 'Property Features'

    @property
    def unit_amenities_label(self):
        """
        Heading for the private card.

        A room rental is not a unit — the tenant gets a bedroom inside someone
        else's home — so the wording follows what is actually being let.
        """
        if getattr(self, 'accommodation_type', None) == 'room':
            return 'Room Features'
        return 'In-Unit Features'

    @property
    def has_amenity_cards(self):
        """True when either catalogue has something to show."""
        return bool(self.community_amenities_list or self.in_unit_amenities_list)

class GalleryDisplayMixin:
    """
    Read-only helpers for the photo collage on a detail page.

    The collage is a mosaic paged left and right, so every page has to fill its
    grid exactly — a half-empty page reads as a broken layout, not as "that was
    all the photos". The grid is four columns by two rows, which is eight cells,
    and `COLLAGE_SPANS` says how a page of `n` photos covers those eight: the
    spans in each row always add up to eight cells, so the last page fills as
    completely as the first no matter how many photos are left over.

    Page sizes alternate 5, 8, 5, 8 …: a five-photo page is one big photo plus
    four small, an eight-photo page is a plain grid, and alternating them keeps
    a long gallery from looking like contact sheets.
    """

    #: Photos per collage page, cycled in order.
    COLLAGE_PAGE_SIZES = (5, 8)

    #: (column span, row span) per tile, keyed by how many photos are on the page.
    #: Each list covers all 8 cells of the 4x2 grid.
    COLLAGE_SPANS = {
        1: [(4, 2)],
        2: [(2, 2), (2, 2)],
        3: [(2, 2), (2, 1), (2, 1)],
        4: [(2, 1), (2, 1), (2, 1), (2, 1)],
        5: [(2, 2), (1, 1), (1, 1), (1, 1), (1, 1)],
        6: [(2, 1), (2, 1), (1, 1), (1, 1), (1, 1), (1, 1)],
        7: [(2, 1)] + [(1, 1)] * 6,
        8: [(1, 1)] * 8,
    }

    @cached_property
    def gallery_urls(self):
        """
        Every photo URL for this place, in display order.

        Falls back to the single legacy `image` field so a listing imported or
        created before the gallery existed still has something to show.
        """
        urls = [img.image.url for img in self.images.all() if img.image]
        if not urls:
            legacy = getattr(self, 'image', None)
            if legacy:
                urls = [legacy.url]
        return urls

    @cached_property
    def collage_pages(self):
        """
        The gallery cut into collage pages.

        Each tile carries its index into `gallery_urls`, which is what the
        viewer opens on when the tile is clicked.
        """
        urls = self.gallery_urls
        pages, start, page_no = [], 0, 0
        while start < len(urls):
            size = self.COLLAGE_PAGE_SIZES[page_no % len(self.COLLAGE_PAGE_SIZES)]
            chunk = urls[start:start + size]
            spans = self.COLLAGE_SPANS[len(chunk)]
            pages.append([
                {'url': url, 'index': start + n, 'cols': spans[n][0], 'rows': spans[n][1]}
                for n, url in enumerate(chunk)
            ])
            start += size
            page_no += 1
        return pages


class Listing(GalleryDisplayMixin, AmenityDisplayMixin, ProximityDisplayMixin, models.Model):
    CATEGORY_CHOICES = [
        ('roommates', 'Roommates'),
        ('rentals', 'Rentals'),
        ('properties', 'Properties'),
        ('local_services', 'Local Services'),
        ('jobs', 'Jobs'),
        ('buy_sell', 'Buy & Sell'),
        ('events', 'Events'),
    ]

    ACCOMMODATION_TYPE_CHOICES = [
        ('room',  'Room'),
        ('whole', 'Whole property'),
    ]
    PROPERTY_TYPE_CHOICES = [
        # Rental types
        ('apartment',     'Apartment'),
        ('condo',         'Condo'),
        ('house',         'House'),
        ('townhouse',     'Townhouse'),
        ('basement',      'Basement'),
        ('loft',          'Loft'),
        ('studio',        'Studio'),
        ('trailer',       'Trailer'),
        # Buy / Properties types
        ('single_family', 'Single-Family Home'),
        ('ranch_house',   'Ranch House'),
        ('land',          'Land'),
        ('ranch',         'Ranch'),
    ]

    PRICE_UNIT_CHOICES = [
        ('',    '— select —'),
        ('mo',  '/Month'),
        ('wk',  '/Week'),
        ('day', '/Day'),
        ('hr',  '/Hour'),
    ]

    STATUS_CHOICES = [
        ('active',         'Active'),
        ('draft',          'Draft'),
        ('on_hold',        'On Hold'),
        ('closed',         'Closed'),
        ('pending',        'Pending Review'),
        ('flagged',        'Flagged'),
        ('under_contract', 'Under Contract'),
        ('sold',           'Sold'),
    ]

    SOURCE_CHOICES = [
        ('native',      'Native'),
        ('mls_ntreis',  'NTREIS MLS'),
        ('partner_csv', 'Partner CSV'),
    ]

    # SET_NULL, not CASCADE: inventory outlives the account that entered it.
    # For partner rows the company holds it via `organization`; for a native
    # listing this leaves an unclaimed row rather than silently destroying it.
    owner = models.ForeignKey(User, null=True, blank=True,
                              on_delete=models.SET_NULL, related_name='listings')
    title = models.CharField(max_length=120)
    description = models.TextField()
    price = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    price_unit = models.CharField(max_length=8, choices=PRICE_UNIT_CHOICES, blank=True, default='')
    category = models.CharField(max_length=32, choices=CATEGORY_CHOICES, default='')
    address_line = models.CharField(max_length=200, blank=True, default='',
                                    help_text='Street address, e.g. 4521 Maple Ave')
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100, blank=True)
    country = models.CharField(max_length=100, default='USA')
    zip_code = models.CharField(max_length=20, blank=True, default='')
    contact_phone = models.CharField(max_length=30, blank=True)
    accommodation_type = models.CharField(max_length=20, choices=ACCOMMODATION_TYPE_CHOICES, blank=True, default='')
    property_type      = models.CharField(max_length=20, choices=PROPERTY_TYPE_CHOICES, blank=True, default='')
    bills_included     = models.BooleanField(default=False)
    security_deposit   = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    available_from = models.DateField(blank=True, null=True,
                                      help_text='Date the listing becomes available (leave blank if available now)')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    featured = models.BooleanField(default=False)
    image = models.ImageField(upload_to='listing_images/', blank=True, null=True)
    tags = models.CharField(max_length=1000, blank=True, default='',
                            help_text='Comma-separated tags, e.g. pet-friendly, parking, furnished')

    # Displayed as two catalogues, not as search filters — `tags` stays the
    # filterable field. The help text carries the shared/private split because
    # there is no controlled vocabulary: whoever types the row decides.
    community_amenities = models.CharField(max_length=2000, blank=True, default='',
        help_text='Shared or outside your door, comma-separated: Pool, Gym, Dog Park, Gated Entry')
    in_unit_amenities   = models.CharField(max_length=2000, blank=True, default='',
        help_text='Yours alone, behind your door, comma-separated: Washer/Dryer, Dishwasher, Balcony')
    created_at = models.DateTimeField(auto_now_add=True)
    view_count = models.PositiveIntegerField(default=0)
    bedrooms   = models.PositiveSmallIntegerField(null=True, blank=True,
                     help_text='Number of bedrooms (leave blank if not applicable)')

    # ── Properties-for-sale fields ────────────────────────────────────────
    square_footage = models.PositiveIntegerField(null=True, blank=True)
    year_built     = models.PositiveSmallIntegerField(null=True, blank=True)
    hoa_fee        = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    original_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True,
                         help_text='Original asking price — used to show Price Reduced badge')

    # ── Listing lifecycle ─────────────────────────────────────────────────
    expires_at = models.DateField(null=True, blank=True,
                     help_text='Listing auto-expires on this date (leave blank for no expiry)')

    # ── Data source ───────────────────────────────────────────────────────
    source_type = models.CharField(max_length=20, choices=SOURCE_CHOICES, default='native')
    # Partner-supplied rows carry the partner's own identifier so re-imports
    # update the same row. Matching on address is unreliable — one formatting
    # change from the partner and the same unit imports twice.
    source_listing_id = models.CharField(max_length=120, blank=True, default='', db_index=True,
                            help_text="The partner's own ID for this unit. Blank for native listings.")
    # Partner-supplied rows belong to a company, not a person. Null for native
    # listings, which an individual landlord genuinely does own via `owner`.
    organization = models.ForeignKey('partners.Organization', null=True, blank=True,
                                     on_delete=models.SET_NULL, related_name='listings')
    # Blueprint §13: a listing absent from one feed run is only *pending*
    # deactivation. A second run that also omits it closes it. This is what
    # stops a truncated upload from wiping a partner's inventory.
    deactivation_pending_since = models.DateTimeField(null=True, blank=True,
                                     help_text='Set when a partner feed first omitted this row.')

    # ── Community unit link ───────────────────────────────────────────────
    parent = models.ForeignKey('self', null=True, blank=True, on_delete=models.SET_NULL, related_name='units')
    is_community = models.BooleanField(default=False)

    # ── Unit / floor-plan detail fields (used when listing is a child unit) ──
    bathrooms        = models.DecimalField(max_digits=3, decimal_places=1, null=True, blank=True)
    floor_plan_image = models.ImageField(upload_to='floor_plan_images/', null=True, blank=True)
    virtual_tour_url = models.URLField(max_length=500, blank=True, default='')

    # ── Geocoding (real map coordinates) ──────────────────────────────────
    latitude  = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True, db_index=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True, db_index=True)
    geocoded_address = models.CharField(max_length=300, blank=True, default='',
                          help_text='The address string last sent to the geocoder — used to detect changes')

    # ── Walk Score (walkability / transit / bike) ─────────────────────────
    # Populated from lat/lng by listings.services.walkscore. Nullable because a
    # score is only available once the row is geocoded and the API has data.
    walk_score             = models.PositiveSmallIntegerField(null=True, blank=True, db_index=True)
    walk_score_description = models.CharField(max_length=60, blank=True, default='')
    transit_score          = models.PositiveSmallIntegerField(null=True, blank=True)
    transit_description    = models.CharField(max_length=60, blank=True, default='')
    bike_score             = models.PositiveSmallIntegerField(null=True, blank=True)
    bike_description       = models.CharField(max_length=60, blank=True, default='')
    walk_score_link        = models.URLField(max_length=500, blank=True, default='',
                                 help_text="Attribution link back to Walk Score — required by their API terms")
    walk_score_updated     = models.DateTimeField(null=True, blank=True,
                                 help_text='When the scores were last fetched — used to detect staleness')

    # ── Nearby schools (GreatSchools) ─────────────────────────────────────
    # The schools themselves live in `School`, joined through `ListingSchool`.
    # Only the fetch timestamp is per-listing, because staleness is a fact
    # about this listing's last sync, not about any school.
    schools_updated = models.DateTimeField(null=True, blank=True,
                          help_text='When nearby schools were last fetched — used to detect staleness')

    # ── Nearest downtown ──────────────────────────────────────────────────
    # Denormalised from the Downtown table by listings.services.downtowns.
    # Stored rather than computed per render so list pages can order and filter
    # on it without loading every downtown for every row. SET_NULL because
    # retiring a downtown must not delete listings.
    nearest_downtown = models.ForeignKey('Downtown', null=True, blank=True,
                           on_delete=models.SET_NULL, related_name='listings')
    downtown_distance_miles = models.DecimalField(max_digits=5, decimal_places=1,
                                  null=True, blank=True, db_index=True)
    # Typical no-traffic drive, from listings.services.drivetime. Null until the
    # Routes sync runs, or when no drivable route exists — the card falls back
    # to straight-line miles rather than hiding.
    downtown_drive_minutes = models.PositiveSmallIntegerField(null=True, blank=True)
    # Road distance from the same Routes call. Kept beside the straight-line
    # value rather than replacing it: downtown_distance_miles is what matching
    # and ordering use, and it is the fallback when no route resolves.
    downtown_drive_miles = models.DecimalField(max_digits=5, decimal_places=1,
                               null=True, blank=True)

    # ── Nearby groceries (Google Places) ──────────────────────────────────
    groceries_updated = models.DateTimeField(null=True, blank=True,
                            help_text='When nearby groceries were last fetched — used to detect staleness')

    # ── Drive times (Google Routes) ───────────────────────────────────────
    drive_times_updated = models.DateTimeField(null=True, blank=True,
                              help_text='When drive times were last fetched — used to detect staleness')

    # ── Transit + Commute Score (GTFS) ────────────────────────────────────
    # Stations live in `TransitStation`, joined through `ListingTransitStation`.
    transit_updated = models.DateTimeField(null=True, blank=True,
                          help_text='When nearby stations were last matched — used to detect staleness')
    # Listojo's own 0-100 commute measure, from listings.services.commute_score.
    # Stored rather than computed per render so search can filter and order on
    # it; db_index because that is the only reason to store it at all.
    commute_score = models.PositiveSmallIntegerField(null=True, blank=True, db_index=True,
                        help_text='0-100 composite: rail access, network reach, frequent service, downtown drive')
    commute_score_label = models.CharField(max_length=40, blank=True, default='',
                              help_text="Band name shown under the score, e.g. 'Excellent Transit'")

    INCOME_QUALIFIER_CATEGORIES = {'rentals', 'roommates'}

    @property
    def full_address(self):
        """Single-line address used for geocoding."""
        parts = [self.address_line, self.city, self.state, self.zip_code, self.country]
        return ', '.join(p.strip() for p in parts if p and p.strip())

    @property
    def school_cards(self):
        """
        Nearby schools for display, ordered elementary → middle → high.

        Deliberately a bare `.all()`: that is the only form that reuses a
        `prefetch_related('nearby_schools__school')` on the caller's queryset.
        Adding a filter or select_related here would silently re-query per
        listing on any page showing more than one.
        """
        return self.nearby_schools.all()

    def get_tags_list(self):
        return [t.strip() for t in self.tags.split(',') if t.strip()]

    def recommended_income(self):
        """3× monthly rent rule, only for rental categories."""
        if self.category in self.INCOME_QUALIFIER_CATEGORIES and self.price:
            return int(self.price * 3)
        return None

    def clean(self):
        errors = {}
        if self.original_price and self.price and self.original_price <= self.price:
            errors['original_price'] = 'Original price must be greater than the current price to show a Price Reduced badge.'
        if self.year_built:
            import datetime
            current_year = datetime.date.today().year
            if self.year_built < 1800 or self.year_built > current_year + 2:
                errors['year_built'] = f'Year built must be between 1800 and {current_year + 2}.'
        if self.expires_at and self.category == 'properties' and self.status in ('under_contract', 'sold'):
            errors['expires_at'] = 'Sold or under-contract listings should not have an expiry date.'
        if self.hoa_fee is not None and self.hoa_fee < 0:
            errors['hoa_fee'] = 'HOA fee cannot be negative.'
        if self.square_footage is not None and self.square_footage == 0:
            errors['square_footage'] = 'Square footage must be greater than zero.'
        if errors:
            raise ValidationError(errors)

    class Meta:
        ordering = ['-featured', '-created_at']

    def __str__(self):
        return self.title


class ListingImage(models.Model):
    listing = models.ForeignKey(Listing, on_delete=models.CASCADE, related_name='images')
    image   = models.ImageField(upload_to='listing_images/')
    order   = models.PositiveSmallIntegerField(default=0)
    #: The feed URL this came from. Blank means a person uploaded it, which is
    #: what keeps an import from deleting hand-added photos.
    source_url = models.URLField(max_length=500, blank=True, default='')

    class Meta:
        ordering = ['order', 'id']

    def __str__(self):
        return f'Image {self.order} for {self.listing.title}'


class Favourite(models.Model):
    user    = models.ForeignKey(User, on_delete=models.CASCADE, related_name='favourites')
    listing = models.ForeignKey(Listing, on_delete=models.CASCADE, related_name='favourited_by')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'listing')

    def __str__(self):
        return f'{self.user.username} ♥ {self.listing.title}'


class CityWaitlist(models.Model):
    email      = models.EmailField()
    city       = models.CharField(max_length=100)
    state      = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('email', 'city')
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.email} — {self.city}'


class GuidedSearchEvent(models.Model):
    START    = 'start'
    COMPLETE = 'complete'
    TYPE_CHOICES = [(START, 'Start'), (COMPLETE, 'Complete')]

    event_type = models.CharField(max_length=10, choices=TYPE_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'GuidedSearch {self.event_type} at {self.created_at}'


class ListingInquiry(models.Model):
    listing = models.ForeignKey(Listing, on_delete=models.CASCADE, related_name='inquiries')
    name = models.CharField(max_length=120)
    email = models.EmailField()
    phone = models.CharField(max_length=30, blank=True)
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    is_read = models.BooleanField(default=False)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'Inquiry for {self.listing.title} by {self.name}'


class UserListingEvent(models.Model):
    """
    Records every user interaction with a listing — the training data
    for the LightGBM Ranker.  Snapshots of listing and user features
    are frozen at event time so future model retrains stay accurate
    even after listings change price or status.
    """
    IMPRESSION   = 'impression'
    CLICK        = 'click'
    SAVE         = 'save'
    UNSAVE       = 'unsave'
    CONTACT      = 'contact'
    REJECT       = 'reject'
    TOUR_REQUEST = 'tour_request'

    EVENT_TYPES = [
        (IMPRESSION,   'Impression'),
        (CLICK,        'Click'),
        (SAVE,         'Save'),
        (UNSAVE,       'Unsave'),
        (CONTACT,      'Contact'),
        (REJECT,       'Reject'),
        (TOUR_REQUEST, 'Tour Request'),
    ]

    # ML training label: higher = stronger positive signal
    LABEL_MAP = {
        IMPRESSION:   0,
        CLICK:        1,
        SAVE:         2,
        UNSAVE:       0,
        CONTACT:      3,
        TOUR_REQUEST: 4,
        REJECT:       -1,
    }

    user        = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name='listing_events')
    session_key = models.CharField(max_length=40, blank=True, default='')
    listing     = models.ForeignKey(Listing, null=True, blank=True, on_delete=models.CASCADE, related_name='events')
    community   = models.ForeignKey('Community', null=True, blank=True, on_delete=models.CASCADE, related_name='events')
    event_type  = models.CharField(max_length=20, choices=EVENT_TYPES)
    label       = models.SmallIntegerField(default=0)

    # Search-session context
    search_id     = models.UUIDField(null=True, blank=True, db_index=True)
    rank_position = models.PositiveSmallIntegerField(null=True, blank=True)
    fmm_score     = models.FloatField(null=True, blank=True)

    # Feature snapshots frozen at event time
    user_features_snapshot    = models.JSONField(default=dict)
    listing_features_snapshot = models.JSONField(default=dict)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'listing', 'event_type']),
            models.Index(fields=['session_key', 'listing']),
            models.Index(fields=['user', 'community', 'event_type']),
            models.Index(fields=['session_key', 'community']),
        ]
        verbose_name = 'User Listing Event'

    def __str__(self):
        who = self.user or self.session_key[:8]
        if self.listing_id:
            target = f'listing {self.listing_id}'
        else:
            target = f'community {self.community_id}'
        return f'{self.event_type} by {who} on {target}'


# ── Community models ──────────────────────────────────────────────────────────

class Community(AmenityDisplayMixin, ProximityDisplayMixin, models.Model):
    STATUS_CHOICES = [
        ('active',   'Active'),
        ('draft',    'Draft'),
        ('inactive', 'Inactive'),
    ]

    COMMUNITY_TYPE_CHOICES = [
        ('apartment_complex', 'Apartment Complex'),
        ('condo_building',    'Condo Building'),
        ('townhouse_complex', 'Townhouse Complex'),
        ('mixed_use',         'Mixed Use'),
        ('student_housing',   'Student Housing'),
        ('senior_living',     'Senior Living'),
        ('other',             'Other'),
    ]

    # SET_NULL for the same reason as Listing.owner — a building must survive
    # the departure of whoever keyed it in. Management lives in `managed_by`.
    owner          = models.ForeignKey(User, null=True, blank=True,
                                       on_delete=models.SET_NULL, related_name='communities')
    name           = models.CharField(max_length=120)
    description    = models.TextField()
    address_line   = models.CharField(max_length=200, blank=True)
    city           = models.CharField(max_length=100)
    state          = models.CharField(max_length=100, blank=True)
    zip_code       = models.CharField(max_length=20, blank=True)
    country        = models.CharField(max_length=100, default='USA')
    contact_phone  = models.CharField(max_length=30, blank=True)
    contact_email  = models.EmailField(blank=True)
    website        = models.URLField(blank=True)

    community_amenities = models.CharField(max_length=2000, blank=True,
        help_text='Comma-separated: Pool, Gym, Dog Park, Rooftop')
    in_unit_amenities   = models.CharField(max_length=2000, blank=True,
        help_text='Comma-separated: Washer/Dryer, Dishwasher, Balcony')

    pet_policy         = models.CharField(max_length=500, blank=True)
    parking_info       = models.CharField(max_length=500, blank=True)
    utilities_included = models.CharField(max_length=500, blank=True)
    lease_terms        = models.CharField(max_length=200, blank=True)
    special_offer      = models.CharField(max_length=200, blank=True)

    community_type = models.CharField(
        max_length=30, choices=COMMUNITY_TYPE_CHOICES,
        blank=True, default='',
    )
    # ── Management ────────────────────────────────────────────────────────
    # The company that currently manages this property. SET_NULL, never CASCADE:
    # a building outlives the company managing it. History lives in
    # partners.ManagementAssignment; the partner's own ID for this property
    # lives in partners.SourceRecordMap.
    managed_by = models.ForeignKey('partners.Organization', null=True, blank=True,
                                   on_delete=models.SET_NULL, related_name='communities')
    # Display rights come from the managing partner's agreement (blueprint §14),
    # so they do not survive a change of manager.
    media_rights_confirmed = models.BooleanField(default=False,
                                 help_text='Partner has authorized Listojo to display this media.')
    # Who asserted it and when. The claim is the partner's to make, so the
    # record has to name a person — a lone boolean cannot answer "says who?"
    # if a photo's use is ever challenged.
    media_rights_confirmed_by = models.ForeignKey(User, null=True, blank=True,
                                 on_delete=models.SET_NULL, related_name='+')
    media_rights_confirmed_at = models.DateTimeField(null=True, blank=True)
    status   = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    featured = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    # ── Geocoding (real map coordinates) ──────────────────────────────────
    latitude  = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True, db_index=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True, db_index=True)
    geocoded_address = models.CharField(max_length=300, blank=True, default='',
                          help_text='The address string last sent to the geocoder — used to detect changes')

    class Meta:
        ordering = ['-featured', '-created_at']
        verbose_name_plural = 'communities'

    def __str__(self):
        return self.name

    # ── Proximity ─────────────────────────────────────────────────────────
    # The same columns Listing carries, for the same reason: a community is a
    # point on a map, and every proximity service already takes a bare
    # instance. Duplicated here rather than shared because the tables are
    # separate; the display logic is not — see ProximityDisplayMixin.
    walk_score             = models.PositiveSmallIntegerField(null=True, blank=True, db_index=True)
    walk_score_description = models.CharField(max_length=60, blank=True, default='')
    transit_score          = models.PositiveSmallIntegerField(null=True, blank=True)
    transit_description    = models.CharField(max_length=60, blank=True, default='')
    bike_score             = models.PositiveSmallIntegerField(null=True, blank=True)
    bike_description       = models.CharField(max_length=60, blank=True, default='')
    walk_score_link        = models.URLField(max_length=500, blank=True, default='',
                                 help_text="Attribution link back to Walk Score — required by their API terms")
    walk_score_updated     = models.DateTimeField(null=True, blank=True,
                                 help_text='When the scores were last fetched — used to detect staleness')

    nearest_downtown = models.ForeignKey('Downtown', null=True, blank=True,
                           on_delete=models.SET_NULL, related_name='communities')
    downtown_distance_miles = models.DecimalField(max_digits=5, decimal_places=1,
                                  null=True, blank=True, db_index=True)
    downtown_drive_minutes = models.PositiveSmallIntegerField(null=True, blank=True)
    downtown_drive_miles = models.DecimalField(max_digits=5, decimal_places=1,
                               null=True, blank=True)

    groceries_updated = models.DateTimeField(null=True, blank=True,
                            help_text='When nearby groceries were last fetched — used to detect staleness')
    drive_times_updated = models.DateTimeField(null=True, blank=True,
                              help_text='When drive times were last fetched — used to detect staleness')
    transit_updated = models.DateTimeField(null=True, blank=True,
                          help_text='When nearby stations were last matched — used to detect staleness')
    commute_score = models.PositiveSmallIntegerField(null=True, blank=True, db_index=True,
                        help_text='0-100 composite: rail access, network reach, frequent service, downtown drive')
    commute_score_label = models.CharField(max_length=40, blank=True, default='',
                              help_text="Band name shown under the score, e.g. 'Excellent Transit'")

    @property
    def full_address(self):
        """Single-line address used for geocoding."""
        parts = [self.address_line, self.city, self.state, self.zip_code, self.country]
        return ', '.join(p.strip() for p in parts if p and p.strip())

    @property
    def shared_amenities_label(self):
        """Always the community wording — a Community is by definition a complex."""
        return 'Community Amenities'

    @property
    def price_range(self):
        from django.db.models import Min, Max
        result = Unit.objects.filter(
            floor_plan__community=self, status='available', price__isnull=False
        ).aggregate(mn=Min('price'), mx=Max('price'))
        return result['mn'], result['mx']

    @property
    def available_unit_count(self):
        return Unit.objects.filter(floor_plan__community=self, status='available').count()

    @property
    def bedroom_types(self):
        return list(
            FloorPlan.objects.filter(community=self)
            .values_list('bedrooms', flat=True)
            .distinct()
            .order_by('bedrooms')
        )

    def get_first_image(self):
        return self.images.first()


class CommunityImage(models.Model):
    community = models.ForeignKey(Community, on_delete=models.CASCADE, related_name='images')
    image     = models.ImageField(upload_to='community_images/')
    order     = models.PositiveSmallIntegerField(default=0)
    #: See ListingImage.source_url.
    source_url = models.URLField(max_length=500, blank=True, default='')

    class Meta:
        ordering = ['order', 'id']

    def __str__(self):
        return f'Image {self.order} for {self.community.name}'


class FloorPlan(models.Model):
    community     = models.ForeignKey(Community, on_delete=models.CASCADE, related_name='floor_plans')
    name          = models.CharField(max_length=80, help_text='e.g. "The Magnolia" or "2BR Classic"')
    bedrooms      = models.PositiveSmallIntegerField(default=1)
    bathrooms     = models.DecimalField(max_digits=3, decimal_places=1, default=1.0)
    square_footage = models.PositiveIntegerField(null=True, blank=True)
    floor_plan_image = models.ImageField(upload_to='floor_plan_images/', null=True, blank=True)
    description   = models.TextField(blank=True)

    class Meta:
        ordering = ['bedrooms', 'square_footage']

    def __str__(self):
        return f'{self.name} ({self.bedrooms}BR)'

    @property
    def available_units(self):
        return self.units.filter(status='available')

    @property
    def price_range(self):
        from django.db.models import Min, Max
        result = self.units.filter(status='available', price__isnull=False).aggregate(
            mn=Min('price'), mx=Max('price')
        )
        return result['mn'], result['mx']


class SavedSearch(models.Model):
    SEARCH_TYPE_CHOICES = [
        ('rent', 'Rent'),
        ('buy',  'Buy'),
    ]

    user              = models.ForeignKey(User, on_delete=models.CASCADE, related_name='saved_searches')
    search_type       = models.CharField(max_length=10, choices=SEARCH_TYPE_CHOICES)
    city              = models.CharField(max_length=100, blank=True)
    max_budget        = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    bedrooms          = models.PositiveSmallIntegerField(null=True, blank=True)
    property_type     = models.CharField(max_length=20, blank=True)
    accommodation_type = models.CharField(max_length=20, blank=True)
    amenities         = models.CharField(max_length=500, blank=True,
                                         help_text='Comma-separated tags from guided search')
    available_by      = models.CharField(max_length=20, blank=True)
    priority          = models.CharField(max_length=20, blank=True)
    urgency           = models.CharField(max_length=20, blank=True)
    monthly_income    = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    last_updated      = models.DateTimeField(auto_now=True)

    # ── Alerts ────────────────────────────────────────────────────────────
    alerts_enabled    = models.BooleanField(default=True,
                            help_text='Send new-match alerts (email/SMS) for this search')
    last_alerted_at   = models.DateTimeField(null=True, blank=True,
                            help_text='Watermark — only listings created after this are alerted')

    class Meta:
        unique_together = [('user', 'search_type')]

    def __str__(self):
        return f'{self.user.username} — {self.get_search_type_display()} search'

    def as_url_params(self) -> str:
        from urllib.parse import urlencode
        params = {
            'fmm': '1',
            'category': 'rentals' if self.search_type == 'rent' else 'properties',
        }
        if self.city:              params['city'] = self.city
        if self.max_budget:        params['max_price'] = str(int(self.max_budget))
        if self.bedrooms:          params['bedrooms'] = str(self.bedrooms)
        if self.property_type:     params['property_type'] = self.property_type
        if self.accommodation_type: params['accommodation_type'] = self.accommodation_type
        if self.amenities:         params['tags'] = self.amenities
        if self.available_by:      params['available_by'] = self.available_by
        return urlencode(params)

    def summary_label(self) -> str:
        """Short human-readable summary for the resume banner."""
        parts = []
        if self.city:
            parts.append(self.city)
        if self.bedrooms:
            parts.append(f'{self.bedrooms}bd')
        if self.max_budget:
            parts.append(f'up to ${int(self.max_budget):,}/mo')
        if self.amenities:
            first_tag = self.amenities.split(',')[0].strip()
            if first_tag:
                parts.append(first_tag)
        return ' · '.join(parts) if parts else self.get_search_type_display()


class Unit(models.Model):
    STATUS_CHOICES = [
        ('available',   'Available'),
        ('occupied',    'Occupied'),
        ('coming_soon', 'Coming Soon'),
        # A unit the partner stopped sending. Distinct from 'occupied' on
        # purpose — we know they withdrew it, not that someone moved in.
        ('withdrawn',   'Withdrawn'),
    ]

    floor_plan   = models.ForeignKey(FloorPlan, on_delete=models.CASCADE, related_name='units')
    unit_number  = models.CharField(max_length=20)
    floor        = models.PositiveSmallIntegerField(null=True, blank=True)
    price        = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    available_from = models.DateField(null=True, blank=True)
    status       = models.CharField(max_length=20, choices=STATUS_CHOICES, default='available')
    notes        = models.CharField(max_length=500, blank=True)

    # ── Partner feed provenance ───────────────────────────────────────────
    source_unit_id = models.CharField(max_length=120, blank=True, default='', db_index=True,
                         help_text="The partner's own ID for this unit. Defaults to unit_number.")
    deactivation_pending_since = models.DateTimeField(null=True, blank=True,
                                     help_text='Set when a partner feed first omitted this unit.')

    class Meta:
        ordering = ['unit_number']

    def __str__(self):
        return f'Unit {self.unit_number}'


# ── School models (GreatSchools) ──────────────────────────────────────────────

class School(models.Model):
    """
    A school as GreatSchools describes it.

    Stored once per campus rather than once per listing, because ratings belong
    to the school: when GreatSchools re-rates a campus, every listing near it
    should move together instead of drifting apart until each one is refetched.
    The one fact that is genuinely per-pair — how far away it is — lives on
    ListingSchool.
    """

    # GreatSchools' level codes, with the rank families actually read them in.
    # Sorting on the raw codes would give 'e', 'h', 'm' — high school before
    # middle — so the rank is stored rather than derived at query time.
    LEVEL_META = [
        ('p', 0, 'Preschool'),
        ('e', 1, 'Elementary'),
        ('m', 2, 'Middle'),
        ('h', 3, 'High'),
    ]

    # The universal-id is the natural key for re-imports. Names and addresses
    # get re-spelled upstream between refreshes; the id does not.
    gs_id       = models.CharField(max_length=40, unique=True,
                      help_text="GreatSchools universal-id — the identity we re-import against")
    name        = models.CharField(max_length=200)
    school_type = models.CharField(max_length=20, blank=True, default='',
                      help_text='public / private / charter, as reported by GreatSchools')

    # Kept as the upstream string ('PK-4', '7, 8', '9-12') rather than parsed
    # into a range: the display in the screenshot is the string, and grade
    # spans are irregular enough that parsing would lose information.
    grade_range = models.CharField(max_length=40, blank=True, default='')
    level_codes = models.CharField(max_length=20, blank=True, default='',
                      help_text="Comma-separated GreatSchools level codes, e.g. 'e,m'")
    level_rank  = models.PositiveSmallIntegerField(default=1,
                      help_text='Sort key derived from level_codes — see LEVEL_META')

    city  = models.CharField(max_length=100, blank=True, default='')
    state = models.CharField(max_length=50, blank=True, default='')

    # All ratings are nullable and independent. GreatSchools does not publish
    # every sub-rating for every school — college readiness is a high-school
    # measure, and newer campuses have no progress data yet — so the card shows
    # whichever rows exist rather than a fixed set.
    rating                   = models.PositiveSmallIntegerField(null=True, blank=True, db_index=True,
                                   help_text='Overall GreatSchools rating, 1-10')
    test_score_rating        = models.PositiveSmallIntegerField(null=True, blank=True)
    college_readiness_rating = models.PositiveSmallIntegerField(null=True, blank=True)
    student_progress_rating  = models.PositiveSmallIntegerField(null=True, blank=True)

    # GreatSchools' terms require the rating to link back to their profile page.
    profile_url = models.URLField(max_length=500, blank=True, default='',
                      help_text='Attribution link back to GreatSchools — required by their API terms')
    updated_at  = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['level_rank', 'name']

    def __str__(self):
        return self.name

    @classmethod
    def rank_for_levels(cls, level_codes: str) -> int:
        """
        Sort rank for a comma-separated level-codes string.

        A campus spanning several levels ('e,m') sorts by its lowest level, so
        a K-8 school lands with the elementary schools where a parent looking
        for one would expect to find it.
        """
        ranks = {code: rank for code, rank, _ in cls.LEVEL_META}
        found = [ranks[c] for c in
                 (part.strip().lower() for part in (level_codes or '').split(','))
                 if c in ranks]
        return min(found) if found else 1

    @property
    def level_label(self) -> str:
        """Human name for the school's lowest level, e.g. 'Elementary'."""
        for _, rank, label in self.LEVEL_META:
            if rank == self.level_rank:
                return label
        return ''

    @property
    def rating_rows(self):
        """
        (label, score) for each sub-rating that has data.

        Empty rows are dropped here rather than guarded for in the template,
        matching how Listing.walk_score_rows handles patchy coverage.
        """
        rows = [
            ('Test Score Rating', self.test_score_rating),
            ('College Readiness Rating', self.college_readiness_rating),
            ('Student Progress Rating', self.student_progress_rating),
        ]
        return [r for r in rows if r[1] is not None]

    @property
    def rating_color(self) -> str:
        """
        Hex fill for the rating circle, banded the way GreatSchools bands it.

        Lives on the model so the detail card and any future list view can't
        drift into two different colour scales for the same number.
        """
        if self.rating is None:
            return '#6b7280'   # grey — unrated, not "bad"
        if self.rating >= 8:
            return '#2b7c9e'   # blue   — above average
        if self.rating >= 5:
            return '#4c8c3f'   # green  — average
        return '#c0642a'       # orange — below average


class ListingSchool(models.Model):
    """
    Joins a listing to a nearby school and records the distance between them.

    Distance is the only field here because it is the only fact that depends on
    both sides. Everything else about the school is on School, so a ratings
    refresh touches one row instead of every listing in the district.
    """

    listing = models.ForeignKey(Listing, on_delete=models.CASCADE, related_name='nearby_schools')
    school  = models.ForeignKey(School, on_delete=models.CASCADE, related_name='listing_links')
    distance_miles = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)

    class Meta:
        # Matches how the cards read: elementary → middle → high, nearest first
        # within a level. Set here so admin and shell reads get it too.
        ordering = ['school__level_rank', 'distance_miles']
        constraints = [
            models.UniqueConstraint(fields=['listing', 'school'],
                                    name='uniq_listing_school'),
        ]

    def __str__(self):
        return f'{self.school.name} — {self.distance_miles} mi'


# ── Downtown proximity ────────────────────────────────────────────────────────

class Downtown(models.Model):
    """
    A city centre a renter might commute to.

    Curated rather than fetched: "downtown" is a district with no authoritative
    point, and a hand-placed coordinate is both free and more stable than
    whatever a search API returns for the word today. Editable in admin so the
    list can grow as the site enters new metros.
    """

    name  = models.CharField(max_length=120, unique=True,
                help_text="Display name, e.g. 'Downtown Dallas'")
    city  = models.CharField(max_length=100)
    state = models.CharField(max_length=50, blank=True, default='')
    latitude  = models.DecimalField(max_digits=9, decimal_places=6)
    longitude = models.DecimalField(max_digits=9, decimal_places=6)
    # Lets a metro be retired from matching without deleting rows that listings
    # still point at.
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        ordering = ['state', 'city']

    def __str__(self):
        return self.name


# ── Grocery proximity ─────────────────────────────────────────────────────────

class GroceryStore(models.Model):
    """
    A grocery store near at least one listing.

    Stored once per store and joined to listings, for the same reason schools
    are: one Walmart serves every listing around it, and a name or address
    correction should land in one row rather than a few hundred.
    """

    # Google's place_id is stable across responses and is what re-syncs match
    # on. Names and addresses get re-formatted upstream; the id does not.
    place_id = models.CharField(max_length=200, unique=True)
    # Canonical chain name ('Walmart'), as resolved by services.groceries. The
    # branch's own name ('Walmart Supercenter') is kept separately so the card
    # can group by chain while still showing which branch it means.
    chain    = models.CharField(max_length=60, db_index=True)
    name     = models.CharField(max_length=200)
    address  = models.CharField(max_length=300, blank=True, default='')
    latitude  = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['chain', 'name']

    def __str__(self):
        return self.name


class ListingGroceryStore(models.Model):
    """
    Links a listing to a nearby grocery store and records the distance.

    Straight-line miles, computed locally by services.distance — the Places
    response carries no distance, and a Directions call per store would cost
    more than the number is worth.
    """

    listing = models.ForeignKey(Listing, on_delete=models.CASCADE, related_name='nearby_groceries')
    store   = models.ForeignKey(GroceryStore, on_delete=models.CASCADE, related_name='listing_links')
    distance_miles = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)
    # Typical no-traffic drive. Kept alongside distance_miles rather than
    # replacing it: a route can fail to resolve, and a distance with no time
    # still reads fine.
    drive_minutes = models.PositiveSmallIntegerField(null=True, blank=True)
    # Road distance, from the same Routes call as drive_minutes. distance_miles
    # stays straight-line because _nearest_per_chain ranks on it before any
    # route is known, and Meta.ordering uses it.
    drive_miles = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)

    class Meta:
        ordering = ['distance_miles']
        constraints = [
            models.UniqueConstraint(fields=['listing', 'store'],
                                    name='uniq_listing_grocery_store'),
        ]

    @property
    def display_miles(self):
        """Road miles when a route resolved, else the straight-line figure."""
        return self.drive_miles or self.distance_miles

    def __str__(self):
        return f'{self.store.name} — {self.distance_miles} mi'


# ── Transit proximity (GTFS) ──────────────────────────────────────────────────

class TransitAgency(models.Model):
    """
    A transit operator whose GTFS feed we import.

    The feed URL lives here rather than in code so a moved feed is an admin
    edit, not a deploy. Agencies publish these as a static zip under an open
    licence, which is the whole reason this feature costs nothing per listing:
    unlike groceries and schools, no request is made on behalf of a listing.
    """

    slug = models.SlugField(max_length=40, unique=True,
               help_text="Short identifier used on the import command, e.g. 'dart'")
    name = models.CharField(max_length=60,
               help_text="Badge name shown on the card, e.g. 'DART'")
    full_name = models.CharField(max_length=160, blank=True, default='',
                    help_text="Legal name from the feed, e.g. 'Dallas Area Rapid Transit'")
    gtfs_url = models.URLField(max_length=500,
                   help_text='Direct link to the agency GTFS zip')
    # Lets an agency be skipped by the importer without deleting the stations
    # listings are already linked to.
    is_active = models.BooleanField(default=True, db_index=True)
    last_imported = models.DateTimeField(null=True, blank=True,
                        help_text='When this feed was last imported')
    # Straight from feed_info.txt. Worth storing because it is how you tell
    # "the import ran and nothing changed" from "the import ran on stale data".
    feed_version = models.CharField(max_length=120, blank=True, default='')

    class Meta:
        ordering = ['name']
        verbose_name_plural = 'transit agencies'

    def __str__(self):
        return self.name


# GTFS route_type → our mode. Only the values that appear in US urban feeds are
# mapped; anything else is skipped rather than guessed at, because an unknown
# mode would land in the card with no sensible badge or weight.
#
# Note that agencies are loose with 5 (cable tram): DART files the McKinney
# Avenue Trolley and the Dallas Streetcar under it. Reading 5 as 'streetcar' is
# what the rider means, even though the spec says otherwise.
GTFS_ROUTE_TYPES = {
    0: 'light_rail',
    1: 'subway',
    2: 'commuter_rail',
    3: 'bus',
    5: 'streetcar',
    11: 'bus',     # trolleybus — a bus for every purpose the card has
    12: 'subway',  # monorail
}

TRANSIT_MODES = [
    ('commuter_rail', 'Commuter Rail'),
    ('subway',        'Subway'),
    ('light_rail',    'Light Rail'),
    ('streetcar',     'Streetcar'),
    ('bus',           'Bus'),
]

# Modes that count as rail for scoring and for the card's ordering. Streetcar
# is deliberately excluded: it shares a lane with traffic and covers a mile or
# two, so it is closer in use to a frequent bus than to a rail line.
RAIL_MODES = ('commuter_rail', 'subway', 'light_rail')

# How the card ranks two routes at the same station. Note this is NOT used to
# rank stations against each other — see services.transit.nearest_stations for
# why distance must win there.
MODE_RANK = {'commuter_rail': 0, 'subway': 1, 'light_rail': 2, 'streetcar': 3, 'bus': 4}

# Badge background when a feed omits route_color. Muted on purpose: a route
# with no colour of its own should not out-shout one that has one.
MODE_BADGE_COLORS = {
    'commuter_rail': '#4b5563',
    'subway':        '#1f2937',
    'light_rail':    '#2a7ef2',
    'streetcar':     '#7c3aed',
    'bus':           '#6b7280',
}


class TransitRoute(models.Model):
    """
    One route (a named line or a numbered bus route) from an agency's feed.

    `trips_per_weekday` is the count on the busiest weekday, which is what
    decides whether the route is frequent. See services.gtfs for why the
    busiest day rather than a nominal Monday.
    """

    agency = models.ForeignKey(TransitAgency, on_delete=models.CASCADE, related_name='routes')
    # GTFS route_id. Unique per agency, not globally — two agencies both having
    # a route '1' is normal, hence the composite constraint below.
    source_id = models.CharField(max_length=120)
    short_name = models.CharField(max_length=60, blank=True, default='',
                    help_text="Badge text, e.g. 'RED' or '705'")
    long_name = models.CharField(max_length=200, blank=True, default='')
    mode = models.CharField(max_length=20, choices=TRANSIT_MODES, db_index=True)
    # GTFS route_color / route_text_color, six hex digits with no '#'. Blank
    # when the feed omits them, in which case the card falls back to the mode
    # palette rather than rendering an invalid colour.
    color = models.CharField(max_length=6, blank=True, default='')
    text_color = models.CharField(max_length=6, blank=True, default='')
    trips_per_weekday = models.PositiveIntegerField(default=0)
    is_frequent = models.BooleanField(default=False, db_index=True,
                      help_text='Runs often enough to be worth showing on its own')

    class Meta:
        ordering = ['agency', 'mode', 'short_name']
        constraints = [
            models.UniqueConstraint(fields=['agency', 'source_id'],
                                    name='uniq_agency_transit_route'),
        ]

    @property
    def label(self):
        """Badge text — the short name when there is one, else the long name."""
        return self.short_name or self.long_name

    @property
    def badge_color(self):
        """Background for the route badge, '#rrggbb'."""
        if self.color:
            return f'#{self.color}'
        return MODE_BADGE_COLORS.get(self.mode, MODE_BADGE_COLORS['bus'])

    @property
    def badge_text_color(self):
        """
        Foreground for the route badge, chosen for contrast rather than taken
        from the feed.

        route_text_color is ignored on purpose. DART publishes the Silver Line
        as C0C0C0 with FFFFFF text, which is white on light grey and effectively
        unreadable; several agencies have a pairing like it. Deriving the
        foreground from the background's luminance means a feed cannot ship us
        an illegible badge.
        """
        raw = self.badge_color.lstrip('#')
        r, g, b = (int(raw[i:i + 2], 16) for i in (0, 2, 4))
        # Rec. 601 luma — good enough to separate light from dark, and cheap.
        return '#111827' if (0.299 * r + 0.587 * g + 0.114 * b) > 150 else '#ffffff'

    def __str__(self):
        return f'{self.agency.name} {self.label}'


class TransitStation(models.Model):
    """
    A stop or station, kept only if it is rail or served frequently enough.

    Filtered at import (see services.gtfs.FREQUENT_TRIPS_PER_WEEKDAY): DART
    alone publishes ~6,800 bus stops with weekday service, so nearly every DFW
    listing sits a quarter mile from one. Storing them all would put a row on
    every listing that says nothing about it.
    """

    agency = models.ForeignKey(TransitAgency, on_delete=models.CASCADE, related_name='stations')
    source_id = models.CharField(max_length=120)
    name = models.CharField(max_length=200)
    latitude  = models.DecimalField(max_digits=9, decimal_places=6)
    longitude = models.DecimalField(max_digits=9, decimal_places=6)
    # Best mode serving the station, by MODE_RANK — a stop where the Red Line
    # meets a bus route is a rail station.
    mode = models.CharField(max_length=20, choices=TRANSIT_MODES, db_index=True)
    # Denormalised from `mode` so proximity queries can filter without an IN
    # over RAIL_MODES on every row.
    is_rail = models.BooleanField(default=False, db_index=True)
    trips_per_weekday = models.PositiveIntegerField(default=0,
                            help_text='All modes, busiest weekday')
    routes = models.ManyToManyField(TransitRoute, through='StationRoute',
                 related_name='stations')
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['agency', 'name']
        constraints = [
            models.UniqueConstraint(fields=['agency', 'source_id'],
                                    name='uniq_agency_transit_station'),
        ]
        indexes = [
            # The proximity scan filters on a lat/lng bounding box before it
            # measures anything — see services.transit.nearest_stations.
            models.Index(fields=['latitude', 'longitude'], name='transit_station_latlng'),
        ]

    @property
    def route_badges(self):
        """
        Routes to show as badges, best mode first.

        A bare `.all()` so a `prefetch_related('...station__routes')` on the
        caller's queryset is reused; ordering is done in Python for the same
        reason, since a filter or order_by here would re-query per station.
        """
        return sorted(self.routes.all(), key=lambda r: (MODE_RANK.get(r.mode, 9), r.label))

    def __str__(self):
        return f'{self.name} ({self.agency.name})'


class StationRoute(models.Model):
    """Join row: this route calls at this station."""

    station = models.ForeignKey(TransitStation, on_delete=models.CASCADE, related_name='route_links')
    route   = models.ForeignKey(TransitRoute, on_delete=models.CASCADE, related_name='station_links')

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['station', 'route'],
                                    name='uniq_station_transit_route'),
        ]

    def __str__(self):
        return f'{self.route.label} @ {self.station.name}'


class ListingTransitStation(models.Model):
    """
    Links a listing to a nearby station and records the distance.

    Same shape as ListingGroceryStore: straight-line miles computed locally at
    match time, with drive figures filled in later by the shared Routes matrix
    call. Walk minutes are derived rather than stored — see `walk_minutes`.
    """

    listing = models.ForeignKey(Listing, on_delete=models.CASCADE, related_name='nearby_transit')
    station = models.ForeignKey(TransitStation, on_delete=models.CASCADE, related_name='listing_links')
    distance_miles = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)
    drive_minutes = models.PositiveSmallIntegerField(null=True, blank=True)
    drive_miles = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)

    class Meta:
        # Rail before bus at equal distance, then nearest first. Matches how the
        # card reads: the line you can catch matters more than a stop 200 feet
        # closer.
        ordering = ['-station__is_rail', 'distance_miles']
        constraints = [
            models.UniqueConstraint(fields=['listing', 'station'],
                                    name='uniq_listing_transit_station'),
        ]

    @property
    def display_miles(self):
        """Road miles when a route resolved, else the straight-line figure."""
        return self.drive_miles or self.distance_miles

    @property
    def walk_minutes(self):
        """
        Rough walk time at 3 mph, for stations close enough that walking is the
        realistic way there.

        Derived rather than stored: it is a fixed multiple of a column we
        already have, and a stored copy would be one more thing to migrate the
        day the assumed pace changes. None beyond a mile, where quoting a walk
        would be misleading.
        """
        if self.distance_miles is None or float(self.distance_miles) > 1.0:
            return None
        return max(1, round(float(self.distance_miles) * 20))

    def __str__(self):
        return f'{self.station.name} — {self.distance_miles} mi'


class CommunityGroceryStore(models.Model):
    """Community counterpart of ListingGroceryStore — same shape, own table."""

    community = models.ForeignKey(Community, on_delete=models.CASCADE,
                                  related_name='nearby_groceries')
    store   = models.ForeignKey(GroceryStore, on_delete=models.CASCADE,
                                related_name='community_links')
    distance_miles = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)
    drive_minutes = models.PositiveSmallIntegerField(null=True, blank=True)
    drive_miles = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)

    class Meta:
        ordering = ['distance_miles']
        constraints = [
            models.UniqueConstraint(fields=['community', 'store'],
                                    name='uniq_community_grocery_store'),
        ]

    def __str__(self):
        return f'{self.store} near {self.community}'

    @property
    def display_miles(self):
        """Road miles when a route resolved, else the straight-line figure."""
        return self.drive_miles or self.distance_miles


class CommunityTransitStation(models.Model):
    """Community counterpart of ListingTransitStation — same shape, own table."""

    community = models.ForeignKey(Community, on_delete=models.CASCADE,
                                  related_name='nearby_transit')
    station = models.ForeignKey(TransitStation, on_delete=models.CASCADE,
                                related_name='community_links')
    distance_miles = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)
    drive_minutes = models.PositiveSmallIntegerField(null=True, blank=True)
    drive_miles = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)

    class Meta:
        # Rail before bus at equal distance, then nearest first — same reason as
        # ListingTransitStation: the line you can catch beats a nearer stop.
        ordering = ['-station__is_rail', 'distance_miles']
        constraints = [
            models.UniqueConstraint(fields=['community', 'station'],
                                    name='uniq_community_transit_station'),
        ]

    def __str__(self):
        return f'{self.station} near {self.community}'

    @property
    def display_miles(self):
        """Road miles when a route resolved, else the straight-line figure."""
        return self.drive_miles or self.distance_miles
