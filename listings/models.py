from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import models


class Listing(models.Model):
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

    INCOME_QUALIFIER_CATEGORIES = {'rentals', 'roommates'}

    @property
    def full_address(self):
        """Single-line address used for geocoding."""
        parts = [self.address_line, self.city, self.state, self.zip_code, self.country]
        return ', '.join(p.strip() for p in parts if p and p.strip())

    @property
    def walk_score_rows(self):
        """
        (label, score, description) for each Walk Score metric that has data.

        Transit and bike coverage is patchy outside dense metros, so rows with
        no score are dropped here rather than guarded for in the template.
        """
        rows = [
            ('Walk Score', self.walk_score, self.walk_score_description),
            ('Transit Score', self.transit_score, self.transit_description),
            ('Bike Score', self.bike_score, self.bike_description),
        ]
        return [r for r in rows if r[1] is not None]

    @property
    def has_walk_scores(self):
        """True when at least one Walk Score metric is available to display."""
        return bool(self.walk_score_rows)

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

    @property
    def grocery_cards(self):
        """
        Nearby grocery stores for display, nearest first.

        A bare `.all()` for the same reason as `school_cards`: it is the only
        form that reuses a prefetch on the caller's queryset.
        """
        return self.nearby_groceries.all()

    @property
    def downtown_display_miles(self):
        """Road miles when a route resolved, else the straight-line figure."""
        return self.downtown_drive_miles or self.downtown_distance_miles

    @property
    def has_drive_times(self):
        """True when any drive time is available — drives the card's footnote."""
        if self.downtown_drive_minutes:
            return True
        return any(link.drive_minutes for link in self.grocery_cards)

    @property
    def has_neighborhood_card(self):
        """True when there is anything to put in the Neighborhood section."""
        return bool(self.nearest_downtown_id) or bool(self.grocery_cards)

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

class Community(models.Model):
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

    @property
    def full_address(self):
        """Single-line address used for geocoding."""
        parts = [self.address_line, self.city, self.state, self.zip_code, self.country]
        return ', '.join(p.strip() for p in parts if p and p.strip())

    def get_amenities_list(self, field):
        val = getattr(self, field, '') or ''
        return [a.strip() for a in val.split(',') if a.strip()]

    @property
    def community_amenities_list(self):
        return self.get_amenities_list('community_amenities')

    @property
    def in_unit_amenities_list(self):
        return self.get_amenities_list('in_unit_amenities')

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
