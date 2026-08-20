from django.contrib import admin

from .models import (CityWaitlist, Community, CommunityImage, Downtown, FloorPlan, GroceryStore,
                     Listing, ListingGroceryStore, ListingInquiry, ListingSchool,
                     ListingTransitStation, School, TransitAgency, TransitRoute,
                     TransitStation, Unit,
                     UserListingEvent)


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


@admin.register(School)
class SchoolAdmin(admin.ModelAdmin):
    list_display  = ('name', 'level_label', 'grade_range', 'rating', 'city', 'state', 'updated_at')
    list_filter   = ('level_rank', 'school_type', 'state', 'city')
    search_fields = ('name', 'gs_id', 'city')
    readonly_fields = ('updated_at',)
    ordering      = ('level_rank', 'name')


@admin.register(ListingSchool)
class ListingSchoolAdmin(admin.ModelAdmin):
    list_display  = ('listing', 'school', 'distance_miles')
    list_filter   = ('school__level_rank',)
    search_fields = ('listing__title', 'school__name')
    # Both sides can run to thousands of rows — raw ids keep the form loadable.
    raw_id_fields = ('listing', 'school')


@admin.register(Downtown)
class DowntownAdmin(admin.ModelAdmin):
    list_display  = ('name', 'city', 'state', 'latitude', 'longitude', 'is_active')
    list_filter   = ('is_active', 'state')
    search_fields = ('name', 'city')


@admin.register(GroceryStore)
class GroceryStoreAdmin(admin.ModelAdmin):
    list_display  = ('name', 'chain', 'address', 'updated_at')
    list_filter   = ('chain',)
    search_fields = ('name', 'address', 'place_id')


@admin.register(ListingGroceryStore)
class ListingGroceryStoreAdmin(admin.ModelAdmin):
    list_display  = ('listing', 'store', 'distance_miles')
    list_filter   = ('store__chain',)
    search_fields = ('listing__title', 'store__name')
    # Both sides can run to thousands of rows — raw ids keep the form loadable.
    raw_id_fields = ('listing', 'store')


@admin.register(TransitAgency)
class TransitAgencyAdmin(admin.ModelAdmin):
    list_display  = ('name', 'slug', 'is_active', 'last_imported', 'feed_version')
    list_filter   = ('is_active',)
    search_fields = ('name', 'slug', 'full_name')
    # gtfs_url is editable on purpose: agencies move their feed, and that should
    # be an admin edit rather than a deploy. See services.gtfs.
    readonly_fields = ('last_imported', 'feed_version')


@admin.register(TransitRoute)
class TransitRouteAdmin(admin.ModelAdmin):
    list_display  = ('label', 'agency', 'mode', 'trips_per_weekday', 'is_frequent')
    list_filter   = ('agency', 'mode', 'is_frequent')
    search_fields = ('short_name', 'long_name', 'source_id')


@admin.register(TransitStation)
class TransitStationAdmin(admin.ModelAdmin):
    list_display  = ('name', 'agency', 'mode', 'is_rail', 'trips_per_weekday')
    list_filter   = ('agency', 'mode', 'is_rail')
    search_fields = ('name', 'source_id')
    # Every field here is overwritten by the next import_gtfs run, so editing
    # one would look like it worked and then silently revert.
    readonly_fields = ('agency', 'source_id', 'name', 'latitude', 'longitude',
                       'mode', 'is_rail', 'trips_per_weekday')


@admin.register(ListingTransitStation)
class ListingTransitStationAdmin(admin.ModelAdmin):
    list_display  = ('listing', 'station', 'distance_miles', 'drive_minutes')
    list_filter   = ('station__agency', 'station__mode')
    search_fields = ('listing__title', 'station__name')
    # Both sides can run to thousands of rows — raw ids keep the form loadable.
    raw_id_fields = ('listing', 'station')
