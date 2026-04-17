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
        ('apartment', 'Apartment'),
        ('condo',     'Condo'),
        ('house',     'House'),
        ('townhouse', 'Townhouse'),
        ('basement',  'Basement'),
        ('loft',      'Loft'),
        ('studio',    'Studio'),
        ('trailer',   'Trailer'),
    ]

    PRICE_UNIT_CHOICES = [
        ('',    '— select —'),
        ('mo',  '/Month'),
        ('wk',  '/Week'),
        ('day', '/Day'),
        ('hr',  '/Hour'),
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
    featured = models.BooleanField(default=False)
    image = models.ImageField(upload_to='listing_images/', blank=True, null=True)
    tags = models.CharField(max_length=1000, blank=True, default='',
                            help_text='Comma-separated tags, e.g. pet-friendly, parking, furnished')
    created_at = models.DateTimeField(auto_now_add=True)

    INCOME_QUALIFIER_CATEGORIES = {'rentals', 'roommates'}

    def get_tags_list(self):
        return [t.strip() for t in self.tags.split(',') if t.strip()]

    def recommended_income(self):
        """3× monthly rent rule, only for rental categories."""
        if self.category in self.INCOME_QUALIFIER_CATEGORIES and self.price:
            return int(self.price * 3)
        return None

    def clean(self):
        pass

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
