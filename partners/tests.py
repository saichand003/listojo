"""
The two failure modes that motivated this app:

  1. A person leaves the company. Their employer's inventory must not follow.
  2. A community changes management company. It must keep its identity, not
     import a second time under the new manager's ID.
"""
import io

from decimal import Decimal

from django.contrib.auth.models import User
from django.db.models import ProtectedError
from django.test import TestCase

from listings.models import Community, Unit
from listings.services.ownership import can_edit_community, editable_communities
from listings.services.partner_import import CsvAdapter, import_partner_inventory
from partners.models import (
    ImportRun,
    ManagementAssignment,
    Membership,
    Organization,
    SourceRecordMap,
    transfer_management,
)

HEADER = ('community_ref,community_name,community_city,floor_plan_name,'
          'unit_number,bedrooms,bathrooms,square_footage,price\n')


class PartnerOwnershipTests(TestCase):
    def setUp(self):
        self.acme = Organization.objects.create(name='Acme Residential', slug='acme',
                                                status='active')
        self.globex = Organization.objects.create(name='Globex Living', slug='globex',
                                                  status='active')
        self.alice = User.objects.create_user(username='alice', password='pw',
                                              email='alice@acme.com')
        self.bob = User.objects.create_user(username='bob', password='pw',
                                            email='bob@globex.com')
        Membership.objects.create(user=self.alice, organization=self.acme, role='owner')
        Membership.objects.create(user=self.bob, organization=self.globex, role='owner')

    def _import(self, body, organization, **kwargs):
        kwargs.setdefault('fetch_photos', False)
        return import_partner_inventory(
            CsvAdapter(io.StringIO(body)), organization=organization, **kwargs)

    # ── 1. People come and go ────────────────────────────────────────────

    def test_deleting_the_person_who_imported_does_not_delete_inventory(self):
        self._import(HEADER + 'MAPLE,Maple Court,Dallas,A1,101,1,1,720,1450\n', self.acme)
        self.assertEqual(Community.objects.count(), 1)

        self.alice.delete()

        # The building and its units survive; only the membership is gone.
        self.assertEqual(Community.objects.count(), 1)
        self.assertEqual(Unit.objects.count(), 1)
        self.assertEqual(Membership.objects.filter(organization=self.acme).count(), 0)
        self.assertEqual(Community.objects.get().managed_by, self.acme)

    def test_removing_a_membership_revokes_access_but_keeps_inventory(self):
        self._import(HEADER + 'MAPLE,Maple Court,Dallas,A1,101,1,1,720,1450\n', self.acme)
        community = Community.objects.get()
        self.assertTrue(can_edit_community(self.alice, community))

        Membership.objects.filter(user=self.alice, organization=self.acme).delete()

        self.assertFalse(can_edit_community(self.alice, community))
        self.assertEqual(Community.objects.count(), 1)

    def test_a_colleague_can_edit_the_same_portfolio(self):
        self._import(HEADER + 'MAPLE,Maple Court,Dallas,A1,101,1,1,720,1450\n', self.acme)
        community = Community.objects.get()

        carol = User.objects.create_user(username='carol', password='pw')
        Membership.objects.create(user=carol, organization=self.acme, role='member')

        # Carol never touched the import, but the company holds the property.
        self.assertTrue(can_edit_community(carol, community))
        self.assertFalse(can_edit_community(self.bob, community))
        self.assertIn(community, editable_communities(carol, Community.objects.all()))
        self.assertNotIn(community, editable_communities(self.bob, Community.objects.all()))

    def test_organization_cannot_be_deleted_while_it_holds_assignments(self):
        self._import(HEADER + 'MAPLE,Maple Court,Dallas,A1,101,1,1,720,1450\n', self.acme)

        with self.assertRaises(ProtectedError):
            self.acme.delete()

    # ── 2. Management changes hands ──────────────────────────────────────

    def test_handover_keeps_one_community_under_a_new_source_id(self):
        self._import(HEADER + 'MAPLE,Maple Court,Dallas,A1,101,1,1,720,1450\n', self.acme)
        community = Community.objects.get()

        transfer_management(community, to_organization=self.globex, note='Acme lost the contract')

        # Globex's PMS calls the same building something else entirely.
        SourceRecordMap.objects.create(
            organization=self.globex, source_id='GLX-77', community=community)
        self._import(HEADER + 'GLX-77,Maple Court,Dallas,A1,101,1,1,720,1525\n', self.globex)

        self.assertEqual(Community.objects.count(), 1, 'handover must not clone the building')
        self.assertEqual(Unit.objects.count(), 1)
        self.assertEqual(Unit.objects.get().price, Decimal('1525'))
        self.assertEqual(Community.objects.get().managed_by, self.globex)

    def test_handover_records_history_on_both_sides(self):
        self._import(HEADER + 'MAPLE,Maple Court,Dallas,A1,101,1,1,720,1450\n', self.acme)
        community = Community.objects.get()

        transfer_management(community, to_organization=self.globex)

        assignments = ManagementAssignment.objects.filter(community=community)
        self.assertEqual(assignments.count(), 2)
        self.assertIsNotNone(assignments.get(organization=self.acme).ended_at)
        self.assertIsNone(assignments.get(organization=self.globex).ended_at)

    def test_previous_manager_cannot_write_after_handover(self):
        self._import(HEADER + 'MAPLE,Maple Court,Dallas,A1,101,1,1,720,1450\n', self.acme)
        community = Community.objects.get()
        transfer_management(community, to_organization=self.globex)

        # Acme's cron fires one more time with stale pricing.
        result = self._import(HEADER + 'MAPLE,Maple Court,Dallas,A1,101,1,1,720,1450\n', self.acme)

        self.assertFalse(result.ok)
        self.assertIn('does not currently manage', result.aborted_reason)
        self.assertEqual(Unit.objects.get().price, Decimal('1450'))

    def test_handover_does_not_withdraw_units_during_the_gap(self):
        self._import(HEADER
                     + 'MAPLE,Maple Court,Dallas,A1,101,1,1,720,1450\n'
                     + 'MAPLE,Maple Court,Dallas,A1,104,1,1,720,1495\n', self.acme)
        community = Community.objects.get()
        transfer_management(community, to_organization=self.globex)

        # Acme imports their remaining portfolio; Maple Court is no longer theirs.
        self._import(HEADER + 'ELM,Elm Tower,Plano,C1,301,1,1,600,1300\n', self.acme)
        self._import(HEADER + 'ELM,Elm Tower,Plano,C1,301,1,1,600,1300\n', self.acme)

        for unit in Unit.objects.filter(floor_plan__community=community):
            self.assertEqual(unit.status, 'available')
            self.assertIsNone(unit.deactivation_pending_since)

    def test_handover_clears_media_rights(self):
        self._import(HEADER + 'MAPLE,Maple Court,Dallas,A1,101,1,1,720,1450\n', self.acme)
        community = Community.objects.get()
        community.media_rights_confirmed = True
        community.save(update_fields=['media_rights_confirmed'])

        transfer_management(community, to_organization=self.globex)

        community.refresh_from_db()
        self.assertFalse(community.media_rights_confirmed,
                         'display rights came from the previous partner agreement')

    def test_import_without_any_member_is_refused(self):
        empty = Organization.objects.create(name='No Staff Co', slug='nostaff')
        result = self._import(HEADER + 'X,X Court,Dallas,A1,101,1,1,720,1450\n', empty)

        self.assertFalse(result.ok)
        self.assertIn('no members', result.aborted_reason)
        self.assertEqual(Community.objects.count(), 0)


class PartnerPortalViewTests(TestCase):
    """The portal is the partner's own surface — access is membership, not staff."""

    def setUp(self):
        self.acme = Organization.objects.create(name='Acme Residential', slug='acme',
                                                status='active')
        self.globex = Organization.objects.create(name='Globex Living', slug='globex',
                                                  status='active')
        self.alice = User.objects.create_user(username='alice', password='pw')
        Membership.objects.create(user=self.alice, organization=self.acme, role='owner')
        self.outsider = User.objects.create_user(username='outsider', password='pw')

    def _csv(self, body, name='inventory.csv'):
        from django.core.files.uploadedfile import SimpleUploadedFile
        return SimpleUploadedFile(name, body.encode(), content_type='text/csv')

    def test_anonymous_is_redirected_to_login(self):
        response = self.client.get('/partners/')
        self.assertEqual(response.status_code, 302)

    def test_user_without_membership_is_refused(self):
        self.client.force_login(self.outsider)
        response = self.client.get('/partners/')
        self.assertEqual(response.status_code, 403)

    def test_member_sees_only_their_own_portfolio(self):
        Community.objects.create(name='Maple Court', description='', city='Dallas',
                                 managed_by=self.acme, status='active')
        Community.objects.create(name='Elm Tower', description='', city='Plano',
                                 managed_by=self.globex, status='active')

        self.client.force_login(self.alice)
        response = self.client.get('/partners/')

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Maple Court')
        self.assertNotContains(response, 'Elm Tower')

    def test_preview_upload_reports_without_writing(self):
        self.client.force_login(self.alice)
        body = (HEADER + 'MAPLE,Maple Court,Dallas,A1,101,1,1,720,1450\n')

        response = self.client.post('/partners/upload/',
                                    {'csv_file': self._csv(body), 'preview': '1'})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Nothing has been published yet')
        self.assertEqual(Community.objects.count(), 0)
        self.assertEqual(ImportRun.objects.count(), 0)

    def test_publish_upload_creates_inventory_and_records_the_run(self):
        self.client.force_login(self.alice)
        body = (HEADER + 'MAPLE,Maple Court,Dallas,A1,101,1,1,720,1450\n')

        response = self.client.post('/partners/upload/',
                                    {'csv_file': self._csv(body), 'apply': '1'}, follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Community.objects.count(), 1)
        self.assertEqual(Community.objects.get().managed_by, self.acme)

        run = ImportRun.objects.get()
        self.assertTrue(run.succeeded)
        self.assertEqual(run.organization, self.acme)
        self.assertEqual(run.started_by, self.alice)
        self.assertEqual(run.filename, 'inventory.csv')

    def test_rejected_rows_are_shown_to_the_partner(self):
        self.client.force_login(self.alice)
        body = (HEADER
                + 'MAPLE,Maple Court,Dallas,A1,101,1,1,720,1450\n'
                + 'MAPLE,Maple Court,Dallas,A1,104,1,1,720,not-a-number\n')

        response = self.client.post('/partners/upload/',
                                    {'csv_file': self._csv(body), 'apply': '1'})

        self.assertEqual(ImportRun.objects.get().rejected_count, 1)
        self.assertEqual(Community.objects.count(), 1)
        # Stays on the upload page so the failed row is actually visible.
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Rows we could not read')
        self.assertContains(response, 'price')

    def test_non_csv_upload_is_rejected(self):
        self.client.force_login(self.alice)
        response = self.client.post(
            '/partners/upload/', {'csv_file': self._csv('nope', name='inventory.xlsx')})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Please upload a .csv file')
        self.assertEqual(ImportRun.objects.count(), 0)

    def test_assisted_onboarding_creates_a_case(self):
        self.client.force_login(self.alice)
        response = self.client.post('/partners/connect/', {
            'pms_name': 'RealPage',
            'syndicates_elsewhere': 'on',
            'syndication_targets': 'Zillow, Apartments.com',
            'technical_contact_email': 'it@acme.com',
            'notes': 'Not sure who owns the feed.',
        }, follow=True)

        self.assertEqual(response.status_code, 200)
        case = self.acme.onboarding_requests.get()
        self.assertEqual(case.pms_name, 'RealPage')
        self.assertTrue(case.syndicates_elsewhere)
        self.assertEqual(case.submitted_by, self.alice)
        self.assertEqual(case.status, 'new')

    def test_upload_history_lists_runs_for_this_org_only(self):
        ImportRun.objects.create(organization=self.acme, summary='acme run')
        ImportRun.objects.create(organization=self.globex, summary='globex run')

        self.client.force_login(self.alice)
        response = self.client.get('/partners/history/')

        self.assertContains(response, 'acme run')
        self.assertNotContains(response, 'globex run')


class PartnerApplicationTests(TestCase):
    """Partner access is applied for, not signed up for."""

    def test_apply_page_is_public(self):
        response = self.client.get('/partners/apply/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Apply to list with Listojo')

    def test_application_creates_a_case_without_an_account(self):
        from partners.models import PartnerApplication

        response = self.client.post('/partners/apply/', {
            'company_name': 'Acme Residential',
            'contact_name': 'Alice Nguyen',
            'contact_email': 'alice@acme.com',
            'portfolio_size': '101-500',
            'markets': 'Dallas, Plano',
            'pms_name': 'RealPage',
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Application received')

        application = PartnerApplication.objects.get()
        self.assertEqual(application.company_name, 'Acme Residential')
        self.assertEqual(application.status, 'new')
        self.assertIsNone(application.organization)
        # No account, no org — staff create those after review.
        self.assertEqual(User.objects.count(), 0)
        self.assertEqual(Organization.objects.count(), 0)

    def test_application_requires_company_and_contact(self):
        from partners.models import PartnerApplication

        response = self.client.post('/partners/apply/', {'company_name': 'Acme'})

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'Application received')
        self.assertEqual(PartnerApplication.objects.count(), 0)


class PartnerApprovalTests(TestCase):
    """Approving is what creates the account — the status field is only a label."""

    def setUp(self):
        from partners.models import PartnerApplication
        self.application = PartnerApplication.objects.create(
            company_name='Oaks Properties',
            contact_name='Sai Chand',
            contact_email='Sai@Oaks.com',
            markets='Dallas, Plano',
        )

    def test_approval_creates_org_account_and_membership(self):
        from partners.services.approval import approve_application

        result = approve_application(self.application)

        organization = Organization.objects.get()
        self.assertEqual(organization.name, 'Oaks Properties')
        self.assertEqual(organization.slug, 'oaks-properties')
        self.assertEqual(organization.contact_email, 'Sai@Oaks.com')

        user = User.objects.get()
        self.assertEqual(user.username, 'Sai@Oaks.com')
        self.assertEqual(user.first_name, 'Sai')
        # Listojo never picks a partner's password.
        self.assertFalse(user.has_usable_password())

        membership = Membership.objects.get()
        self.assertEqual(membership.user, user)
        self.assertEqual(membership.organization, organization)
        self.assertEqual(membership.role, 'owner')

        self.application.refresh_from_db()
        self.assertEqual(self.application.status, 'approved')
        self.assertEqual(self.application.organization, organization)
        self.assertTrue(result.created_user)

    def test_approved_partner_reaches_the_dashboard(self):
        from partners.services.approval import approve_application

        result = approve_application(self.application)
        # Access comes from Membership, never from is_staff.
        self.assertFalse(result.user.is_staff)

        self.client.force_login(result.user)
        response = self.client.get('/partners/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Oaks Properties')

    def test_invite_email_carries_a_working_reset_link(self):
        from django.core import mail
        from partners.services.approval import approve_application

        approve_application(self.application)

        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.to, ['Sai@Oaks.com'])
        self.assertIn('/accounts/reset/', message.body)
        self.assertIn('Sai@Oaks.com', message.body)

        link = [word for word in message.body.split()
                if '/accounts/reset/' in word][0]
        response = self.client.get(link[len('https://listojo.com'):], follow=True)
        self.assertEqual(response.status_code, 200)

    def test_approving_twice_does_not_duplicate_anything(self):
        from django.core import mail
        from partners.services.approval import approve_application

        approve_application(self.application)
        self.application.refresh_from_db()
        second = approve_application(self.application)

        self.assertTrue(second.already_approved)
        self.assertEqual(Organization.objects.count(), 1)
        self.assertEqual(User.objects.count(), 1)
        self.assertEqual(Membership.objects.count(), 1)
        self.assertEqual(len(mail.outbox), 1)

    def test_existing_account_is_reused_not_duplicated(self):
        from partners.services.approval import approve_application

        existing = User.objects.create_user(
            'renter', email='sai@oaks.com', password='pw')

        result = approve_application(self.application)

        self.assertEqual(User.objects.count(), 1)
        self.assertEqual(result.user, existing)
        self.assertFalse(result.created_user)
        # Their existing password must survive being approved as a partner.
        self.assertTrue(result.user.has_usable_password())

    def test_second_company_with_the_same_name_gets_its_own_slug(self):
        from partners.models import PartnerApplication
        from partners.services.approval import approve_application

        approve_application(self.application)
        twin = PartnerApplication.objects.create(
            company_name='Oaks Properties',
            contact_name='Other Person',
            contact_email='other@oaks2.com',
        )

        result = approve_application(twin)

        self.assertEqual(result.organization.slug, 'oaks-properties-2')
        self.assertEqual(Organization.objects.count(), 2)


class PartnerApplicationAdminTests(TestCase):
    """
    Approving through the admin UI, not the service.

    The status dropdown sits beside the bulk action and staff reach for it
    first. It once only wrote a label — an application read 'approved' while no
    organization, account or invite existed.
    """

    def setUp(self):
        from partners.models import PartnerApplication
        self.staff = User.objects.create_superuser(
            'root', 'root@listojo.com', 'pw')
        self.client.force_login(self.staff)
        self.application = PartnerApplication.objects.create(
            company_name='ABC Properties',
            contact_name='Sai Chand',
            contact_email='partner@abc.com',
        )

    def _set_status_via_changelist(self, status):
        """The list_editable dropdown — exactly what staff click."""
        return self.client.post('/admin/partners/partnerapplication/', {
            'form-TOTAL_FORMS': '1',
            'form-INITIAL_FORMS': '1',
            'form-MIN_NUM_FORMS': '0',
            'form-MAX_NUM_FORMS': '1000',
            'form-0-id': str(self.application.pk),
            'form-0-status': status,
            '_save': 'Save',
        }, follow=True)

    def test_status_dropdown_creates_the_account_and_sends_the_invite(self):
        from django.core import mail

        response = self._set_status_via_changelist('approved')
        self.assertEqual(response.status_code, 200)

        organization = Organization.objects.get()
        self.assertEqual(organization.name, 'ABC Properties')

        self.application.refresh_from_db()
        self.assertEqual(self.application.organization, organization)

        membership = Membership.objects.get()
        self.assertEqual(membership.organization, organization)
        self.assertEqual(membership.user.email, 'partner@abc.com')

        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('/accounts/reset/', mail.outbox[0].body)

    def test_other_statuses_create_nothing(self):
        from django.core import mail

        self._set_status_via_changelist('contacted')

        self.application.refresh_from_db()
        self.assertEqual(self.application.status, 'contacted')
        self.assertIsNone(self.application.organization)
        self.assertEqual(Organization.objects.count(), 0)
        self.assertEqual(len(mail.outbox), 0)

    def test_bulk_action_approves_too(self):
        from django.core import mail

        self.client.post('/admin/partners/partnerapplication/', {
            'action': 'approve_and_invite',
            '_selected_action': [str(self.application.pk)],
        }, follow=True)

        self.application.refresh_from_db()
        self.assertEqual(self.application.status, 'approved')
        self.assertIsNotNone(self.application.organization)
        self.assertEqual(len(mail.outbox), 1)

    def test_an_application_stuck_at_approved_can_be_repaired(self):
        """
        The exact prod state after the bug: status says approved, nothing exists.
        Re-running the action must finish the job rather than refuse.
        """
        from django.core import mail

        self.application.status = 'approved'
        self.application.save(update_fields=['status'])

        self.client.post('/admin/partners/partnerapplication/', {
            'action': 'approve_and_invite',
            '_selected_action': [str(self.application.pk)],
        }, follow=True)

        self.application.refresh_from_db()
        self.assertIsNotNone(self.application.organization)
        self.assertEqual(Membership.objects.count(), 1)
        self.assertEqual(len(mail.outbox), 1)


class PartnerSignInRedirectTests(TestCase):
    """
    'Sign in to Listojo Partners' must end at the partner dashboard.

    It once ended on the renter home: the decorator redirected to the login
    page without ?next=, so the destination was gone by the time the partner
    typed their password.
    """

    def test_signed_out_visitor_is_sent_to_login_carrying_the_destination(self):
        response = self.client.get('/partners/')

        self.assertRedirects(response, '/accounts/login/?next=/partners/',
                             fetch_redirect_response=False)

    def test_the_destination_survives_the_otp_step(self):
        """Login is two-legged — ?next= has to outlive the code screen."""
        from partners.models import PartnerApplication
        from partners.services.approval import approve_application

        application = PartnerApplication.objects.create(
            company_name='Oaks Properties',
            contact_name='Sai Chand',
            contact_email='sai@oaks.com',
        )
        user = approve_application(application).user
        user.set_password('pw')
        user.save()

        response = self.client.post('/accounts/login/', {
            'username': user.get_username(),
            'password': 'pw',
            'next': '/partners/',
        })

        self.assertRedirects(response, '/accounts/login/confirm/',
                             fetch_redirect_response=False)
        self.assertEqual(self.client.session['pw_otp_next'], '/partners/')

    def test_an_approved_partner_sees_their_portfolio(self):
        from partners.models import PartnerApplication
        from partners.services.approval import approve_application

        application = PartnerApplication.objects.create(
            company_name='Oaks Properties',
            contact_name='Sai Chand',
            contact_email='sai@oaks.com',
        )
        self.client.force_login(approve_application(application).user)

        response = self.client.get('/partners/')

        self.assertContains(response, 'Oaks Properties')

    def test_already_signed_in_visitor_is_not_bounced_to_the_renter_home(self):
        user = User.objects.create_user('someone', 'someone@example.com', 'pw')
        self.client.force_login(user)

        response = self.client.get('/accounts/login/?next=/partners/')

        self.assertRedirects(response, '/partners/', fetch_redirect_response=False)

    def test_offsite_next_is_ignored(self):
        user = User.objects.create_user('someone', 'someone@example.com', 'pw')
        self.client.force_login(user)

        response = self.client.get('/accounts/login/?next=https://evil.example/')

        self.assertRedirects(response, '/listings/', fetch_redirect_response=False)


class InventoryUploadMessagingTests(TestCase):
    """
    A rejected file must not also claim it imported.

    The footer under the rejection table used to read 'Everything else
    imported' unconditionally — printed directly beneath 'No valid rows found —
    nothing was changed'.
    """

    def setUp(self):
        self.user = User.objects.create_user('pm', 'pm@acme.com', 'pw')
        self.organization = Organization.objects.create(name='Acme', slug='acme')
        Membership.objects.create(user=self.user, organization=self.organization,
                                  role='owner')
        self.client.force_login(self.user)

    def _upload(self, body, *, preview=True):
        upload = io.BytesIO(body.encode())
        upload.name = 'inventory.csv'
        data = {'csv_file': upload, 'preview' if preview else 'publish': '1'}
        return self.client.post('/partners/upload/', data)

    def test_an_unreadable_file_does_not_claim_it_imported(self):
        response = self._upload('photo_urls\nhttps://example.com/a.jpg\n')

        self.assertContains(response, 'Rows we could not read')
        self.assertContains(response, 'Nothing was imported')
        self.assertNotContains(response, 'Everything else imported')

    def test_a_preview_does_not_claim_it_imported(self):
        body = (HEADER
                + 'C1,Acme Place,Dallas,A1,101,1,1,700,1200\n'
                + ',,,,,,,,\n')

        response = self._upload(body)

        # Guard against a vacuous pass: the footer only renders with rejections.
        self.assertContains(response, 'Rows we could not read')
        self.assertContains(response, 'Nothing has been published yet')
        self.assertNotContains(response, 'Everything else imported')


class MediaRightsConfirmationTests(TestCase):
    """
    Rights are the partner's claim, so the partner makes it.

    Before this, the only writable surface was Django admin — which partners
    cannot reach. Their dashboard showed 'Needed' with nothing to click, and a
    staff member ticking the box recorded the wrong party as having asserted it.
    """

    def setUp(self):
        self.organization = Organization.objects.create(name='Acme', slug='acme')
        self.user = User.objects.create_user('pm', 'pm@acme.com', 'pw')
        Membership.objects.create(user=self.user, organization=self.organization,
                                  role='owner')
        self.community = Community.objects.create(
            name='Maple Court', description='', city='Dallas',
            managed_by=self.organization)
        self.client.force_login(self.user)

    def _url(self, community=None):
        return f'/partners/communities/{(community or self.community).pk}/media-rights/'

    def test_confirming_records_who_and_when(self):
        response = self.client.post(self._url())

        self.assertRedirects(response, '/partners/')
        self.community.refresh_from_db()
        self.assertTrue(self.community.media_rights_confirmed)
        self.assertEqual(self.community.media_rights_confirmed_by, self.user)
        self.assertIsNotNone(self.community.media_rights_confirmed_at)

    def test_dashboard_offers_the_button_then_shows_who_confirmed(self):
        response = self.client.get('/partners/')
        self.assertContains(response, 'Confirm rights')

        self.client.post(self._url())

        response = self.client.get('/partners/')
        self.assertNotContains(response, 'Confirm rights')
        self.assertContains(response, 'Confirmed')
        self.assertContains(response, 'pm')

    def test_a_partner_cannot_confirm_another_organizations_community(self):
        other = Organization.objects.create(name='Globex', slug='globex')
        theirs = Community.objects.create(name='Bishop Flats', description='',
                                          city='Dallas', managed_by=other)

        response = self.client.post(self._url(theirs))

        self.assertEqual(response.status_code, 404)
        theirs.refresh_from_db()
        self.assertFalse(theirs.media_rights_confirmed)

    def test_get_does_not_confirm(self):
        response = self.client.get(self._url())

        self.assertEqual(response.status_code, 405)
        self.community.refresh_from_db()
        self.assertFalse(self.community.media_rights_confirmed)

    def test_signed_out_visitor_cannot_confirm(self):
        self.client.logout()

        response = self.client.post(self._url())

        self.assertEqual(response.status_code, 302)
        self.community.refresh_from_db()
        self.assertFalse(self.community.media_rights_confirmed)

    def test_confirming_twice_keeps_the_original_attestation(self):
        self.client.post(self._url())
        self.community.refresh_from_db()
        first_at = self.community.media_rights_confirmed_at

        other_user = User.objects.create_user('colleague', 'c@acme.com', 'pw')
        Membership.objects.create(user=other_user, organization=self.organization)
        self.client.force_login(other_user)
        self.client.post(self._url())

        self.community.refresh_from_db()
        self.assertEqual(self.community.media_rights_confirmed_by, self.user)
        self.assertEqual(self.community.media_rights_confirmed_at, first_at)

    def test_confirming_unblocks_photo_fetching_on_the_next_upload(self):
        """The whole point: `fetch_photos` keys off this flag."""
        self.assertFalse(self.organization.communities.filter(
            media_rights_confirmed=True).exists())

        self.client.post(self._url())

        self.assertTrue(self.organization.communities.filter(
            media_rights_confirmed=True).exists())

    def test_a_change_of_manager_clears_the_attestation(self):
        self.client.post(self._url())
        globex = Organization.objects.create(name='Globex', slug='globex')

        transfer_management(self.community, to_organization=globex)

        self.community.refresh_from_db()
        self.assertFalse(self.community.media_rights_confirmed)
        self.assertIsNone(self.community.media_rights_confirmed_by)
        self.assertIsNone(self.community.media_rights_confirmed_at)
