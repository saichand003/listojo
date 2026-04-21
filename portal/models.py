from django.contrib.auth.models import User
from django.db import models

from listings.models import Listing


class Lead(models.Model):
    SOURCE_CHOICES = [
        ('inquiry',       'Listing Inquiry'),
        ('guided_search', 'Guided Search'),
        ('chat',          'Chat'),
        ('manual',        'Manual Entry'),
    ]
    STATUS_CHOICES = [
        ('new',                     'New'),
        ('contacted',               'Contacted'),
        ('shortlist_ready',         'Shortlist Ready'),
        ('shortlist_sent',          'Shortlist Sent'),
        ('touring',                 'Touring'),
        ('application_in_progress', 'Application In Progress'),
        ('closed_won',              'Closed / Won'),
        ('closed_lost',             'Closed / Lost'),
    ]

    name           = models.CharField(max_length=120)
    email          = models.EmailField()
    phone          = models.CharField(max_length=30, blank=True)
    source         = models.CharField(max_length=20, choices=SOURCE_CHOICES, default='inquiry')
    status         = models.CharField(max_length=30, choices=STATUS_CHOICES, default='new')
    assigned_agent = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                       related_name='assigned_leads')
    listing        = models.ForeignKey(Listing, on_delete=models.SET_NULL, null=True, blank=True,
                                       related_name='leads',
                                       help_text='Listing that triggered this lead')
    notes          = models.TextField(blank=True)
    created_at     = models.DateTimeField(auto_now_add=True)
    updated_at     = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.name} ({self.get_status_display()})'


class LeadPreference(models.Model):
    lead          = models.OneToOneField(Lead, on_delete=models.CASCADE, related_name='preference')
    city          = models.CharField(max_length=100, blank=True)
    max_budget    = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    bedrooms      = models.PositiveSmallIntegerField(null=True, blank=True)
    property_type = models.CharField(max_length=20, blank=True)
    move_in_date  = models.DateField(null=True, blank=True)
    amenities     = models.CharField(max_length=500, blank=True,
                                     help_text='Comma-separated preferred amenities')

    def __str__(self):
        return f'Preferences for {self.lead.name}'


class Shortlist(models.Model):
    STATUS_CHOICES = [
        ('draft',    'Draft'),
        ('sent',     'Sent'),
        ('viewed',   'Viewed'),
        ('archived', 'Archived'),
    ]

    lead       = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name='shortlists')
    agent      = models.ForeignKey(User, on_delete=models.CASCADE, related_name='shortlists')
    status     = models.CharField(max_length=10, choices=STATUS_CHOICES, default='draft')
    sent_at    = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'Shortlist for {self.lead.name} by {self.agent.username}'


class ShortlistItem(models.Model):
    CLIENT_RESPONSE_CHOICES = [
        ('interested', 'Interested'),
        ('rejected',   'Rejected'),
    ]

    shortlist       = models.ForeignKey(Shortlist, on_delete=models.CASCADE, related_name='items')
    listing         = models.ForeignKey(Listing, on_delete=models.CASCADE, related_name='shortlist_items')
    agent_note      = models.TextField(blank=True)
    order_index     = models.PositiveSmallIntegerField(default=0)
    client_response = models.CharField(max_length=10, choices=CLIENT_RESPONSE_CHOICES,
                                       blank=True, null=True)

    class Meta:
        ordering = ['order_index', 'id']

    def __str__(self):
        return f'{self.listing.title} in shortlist for {self.shortlist.lead.name}'
