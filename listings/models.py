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

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'Inquiry for {self.listing.title} by {self.name}'
