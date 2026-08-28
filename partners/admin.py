from django.contrib import admin, messages

from partners.services.approval import approve_application
from partners.models import (
    AssistedOnboardingRequest,
    ImportRun,
    ManagementAssignment,
    Membership,
    PartnerApplication,
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


@admin.register(PartnerApplication)
class PartnerApplicationAdmin(admin.ModelAdmin):
    """
    Inbound partner interest.

    Use the Approve action rather than editing `status` to 'approved' by hand:
    the status field is only a label, while the action is what actually creates
    the organization, the account and the membership.
    """
    list_display = ('company_name', 'contact_name', 'portfolio_size', 'pms_name',
                    'status', 'organization', 'created_at')
    list_filter = ('status', 'portfolio_size', 'pms_name')
    list_editable = ('status',)
    search_fields = ('company_name', 'contact_email', 'markets')
    readonly_fields = ('organization', 'created_at')
    actions = ['approve_and_invite']

    @admin.action(description='Approve — create organization, account and send invite')
    def approve_and_invite(self, request, queryset):
        for application in queryset:
            result = approve_application(application)

            if result.already_approved:
                self.message_user(
                    request,
                    f'{application.company_name} was already approved '
                    f'(organization: {result.organization}). Nothing changed.',
                    messages.WARNING)
                continue

            account = ('created account' if result.created_user
                       else 'linked existing account')
            note = (f'{application.company_name} approved — organization '
                    f'"{result.organization.slug}", {account} '
                    f'{result.user.get_username()}.')

            if result.invite_sent:
                self.message_user(request, f'{note} Invite emailed.', messages.SUCCESS)
            else:
                self.message_user(
                    request,
                    f'{note} The invite email FAILED to send — the account is fine, '
                    f're-run this action to try again.',
                    messages.ERROR)
