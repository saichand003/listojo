from django.contrib import admin

from .models import CityWaitlist, Community, CommunityImage, FloorPlan, Listing, ListingInquiry, Unit, UserListingEvent


@admin.register(Listing)
class ListingAdmin(admin.ModelAdmin):
    list_display = ('title', 'category', 'city', 'country', 'featured', 'owner', 'created_at')
    list_filter = ('category', 'city', 'country', 'featured')
    search_fields = ('title', 'description', 'city', 'state', 'owner__username')


@admin.register(ListingInquiry)
class ListingInquiryAdmin(admin.ModelAdmin):
    list_display = ('listing', 'name', 'email', 'created_at')
    search_fields = ('listing__title', 'name', 'email')


@admin.register(CityWaitlist)
class CityWaitlistAdmin(admin.ModelAdmin):
    list_display  = ('email', 'city', 'state', 'created_at')
    list_filter   = ('city', 'state')
    search_fields = ('email', 'city')
    ordering      = ('-created_at',)


@admin.register(Community)
class CommunityAdmin(admin.ModelAdmin):
    list_display = ('name', 'community_type', 'city', 'status', 'featured', 'owner', 'created_at')
    list_filter = ('community_type', 'status', 'featured', 'city')
    search_fields = ('name', 'city', 'state', 'owner__username')


@admin.register(FloorPlan)
class FloorPlanAdmin(admin.ModelAdmin):
    list_display = ('name', 'community', 'bedrooms', 'bathrooms', 'square_footage')
    list_filter = ('bedrooms', 'community__city')
    search_fields = ('name', 'community__name')


@admin.register(Unit)
class UnitAdmin(admin.ModelAdmin):
    list_display = ('unit_number', 'floor_plan', 'price', 'status', 'available_from')
    list_filter = ('status', 'floor_plan__community__city')
    search_fields = ('unit_number', 'floor_plan__name', 'floor_plan__community__name')


@admin.register(CommunityImage)
class CommunityImageAdmin(admin.ModelAdmin):
    list_display = ('community', 'order')


@admin.register(UserListingEvent)
class UserListingEventAdmin(admin.ModelAdmin):
    list_display = ('event_type', 'listing', 'community', 'user', 'created_at')
    list_filter = ('event_type', 'created_at')
    search_fields = ('listing__title', 'community__name', 'user__username', 'session_key')
