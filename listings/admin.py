from django.contrib import admin

from .models import Listing, ListingInquiry


@admin.register(Listing)
class ListingAdmin(admin.ModelAdmin):
    list_display = ('title', 'category', 'city', 'country', 'featured', 'owner', 'created_at')
    list_filter = ('category', 'city', 'country', 'featured')
    search_fields = ('title', 'description', 'city', 'state', 'owner__username')


@admin.register(ListingInquiry)
class ListingInquiryAdmin(admin.ModelAdmin):
    list_display = ('listing', 'name', 'email', 'created_at')
    search_fields = ('listing__title', 'name', 'email')
