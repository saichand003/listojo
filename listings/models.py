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
        ('native',     'Native'),
        ('mls_ntreis', 'NTREIS MLS'),
    ]

    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='listings')
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

    # ── Community unit link ───────────────────────────────────────────────
    parent = models.ForeignKey('self', null=True, blank=True, on_delete=models.SET_NULL, related_name='units')
    is_community = models.BooleanField(default=False)

    # ── Unit / floor-plan detail fields (used when listing is a child unit) ──
    bathrooms        = models.DecimalField(max_digits=3, decimal_places=1, null=True, blank=True)
    floor_plan_image = models.ImageField(upload_to='floor_plan_images/', null=True, blank=True)
    virtual_tour_url = models.URLField(max_length=500, blank=True, default='')


    INCOME_QUALIFIER_CATEGORIES = {'rentals', 'roommates'}

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

    owner          = models.ForeignKey(User, on_delete=models.CASCADE, related_name='communities')
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
    status   = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    featured = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-featured', '-created_at']
        verbose_name_plural = 'communities'

    def __str__(self):
        return self.name

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
    ]

    floor_plan   = models.ForeignKey(FloorPlan, on_delete=models.CASCADE, related_name='units')
    unit_number  = models.CharField(max_length=20)
    floor        = models.PositiveSmallIntegerField(null=True, blank=True)
    price        = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    available_from = models.DateField(null=True, blank=True)
    status       = models.CharField(max_length=20, choices=STATUS_CHOICES, default='available')
    notes        = models.CharField(max_length=500, blank=True)

    class Meta:
        ordering = ['unit_number']

    def __str__(self):
        return f'Unit {self.unit_number}'
