from django.contrib import admin

from .models import Lead, LeadPreference, Shortlist, ShortlistItem


@admin.register(Lead)
class LeadAdmin(admin.ModelAdmin):
    list_display = ('name', 'email', 'source', 'status', 'listing', 'community', 'assigned_agent', 'created_at')
    list_filter = ('source', 'status', 'assigned_agent')
    search_fields = ('name', 'email', 'listing__title', 'community__name')


@admin.register(LeadPreference)
class LeadPreferenceAdmin(admin.ModelAdmin):
    list_display = ('lead', 'city', 'bedrooms', 'max_budget', 'property_type')
    search_fields = ('lead__name', 'lead__email', 'city')


class ShortlistItemInline(admin.TabularInline):
    model = ShortlistItem
    extra = 0


@admin.register(Shortlist)
class ShortlistAdmin(admin.ModelAdmin):
    list_display = ('lead', 'agent', 'status', 'sent_at', 'created_at')
    list_filter = ('status', 'agent')
    inlines = [ShortlistItemInline]
