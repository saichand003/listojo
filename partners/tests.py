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
