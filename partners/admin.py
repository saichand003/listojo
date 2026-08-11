from django.contrib import admin

from partners.models import (
    AssistedOnboardingRequest,
    ImportRun,
    ManagementAssignment,
    Membership,
    Organization,
    SourceRecordMap,
)


class MembershipInline(admin.TabularInline):
    model = Membership
    extra = 0


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'status', 'created_at')
    list_filter = ('status',)
    search_fields = ('name', 'slug', 'contact_email')
    prepopulated_fields = {'slug': ('name',)}
    inlines = [MembershipInline]


@admin.register(ManagementAssignment)
class ManagementAssignmentAdmin(admin.ModelAdmin):
    list_display = ('community', 'organization', 'started_at', 'ended_at')
    list_filter = ('organization',)


@admin.register(SourceRecordMap)
class SourceRecordMapAdmin(admin.ModelAdmin):
    list_display = ('organization', 'source_id', 'community')
    list_filter = ('organization',)
    search_fields = ('source_id',)


@admin.register(ImportRun)
class ImportRunAdmin(admin.ModelAdmin):
    list_display = ('organization', 'created_at', 'succeeded', 'rejected_count', 'filename')
    list_filter = ('succeeded', 'organization')
    readonly_fields = ('created_at',)


@admin.register(AssistedOnboardingRequest)
class AssistedOnboardingRequestAdmin(admin.ModelAdmin):
    """Blueprint §21 cases land here for Listojo staff to work."""
    list_display = ('organization', 'pms_name', 'status', 'created_at')
    list_filter = ('status', 'pms_name')
    list_editable = ('status',)
    search_fields = ('organization__name', 'technical_contact_email')
