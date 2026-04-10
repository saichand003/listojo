from django.contrib.auth.models import User
from django.db import models


class Listing(models.Model):
    CATEGORY_CHOICES = [
        ('roommates', 'Roommates'),
        ('rentals', 'Rentals'),
        ('local_services', 'Local Services'),
        ('jobs', 'Jobs'),
        ('buy_sell', 'Buy & Sell'),
        ('events', 'Events'),
    ]

    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='listings')
    title = models.CharField(max_length=120)
    description = models.TextField()
    price = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    category = models.CharField(max_length=32, choices=CATEGORY_CHOICES, default='local_services')
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100, blank=True)
    country = models.CharField(max_length=100, default='USA')
    contact_phone = models.CharField(max_length=30, blank=True)
    featured = models.BooleanField(default=False)
    image = models.ImageField(upload_to='listing_images/', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-featured', '-created_at']

    def __str__(self):
        return self.title


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
