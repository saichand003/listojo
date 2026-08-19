import copy
import io
from datetime import date, timedelta
from decimal import Decimal
from unittest import mock

import requests
from django.contrib.auth.models import User
from django.core import mail
from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from django.core.management import call_command

from listings.models import (Community, Downtown, FloorPlan, GroceryStore, GuidedSearchEvent,
                             Listing, ListingGroceryStore, ListingInquiry, ListingSchool, School,
                             Unit, UserListingEvent)
from listings.services import distance, downtowns, drivetime, greatschools, groceries
from portal.models import Lead


class ListingWorkflowTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username='owner',
            password='pw',
            email='owner@example.com',
        )
        self.agent = User.objects.create_user(
            username='agent',
            password='pw',
            email='agent@example.com',
            is_staff=True,
        )
        self.active_listing = Listing.objects.create(
            owner=self.owner,
            title='Active Rental',
            description='Visible listing',
            category='rentals',
            city='Irving',
            price=Decimal('1800.00'),
            bedrooms=2,
            status='active',
            tags='pet-friendly, parking',
        )
        self.expired_listing = Listing.objects.create(
            owner=self.owner,
            title='Expired Rental',
            description='Expired listing',
            category='rentals',
            city='Irving',
            price=Decimal('1500.00'),
            status='active',
            expires_at=date.today() - timedelta(days=1),
        )
        self.other_owner = User.objects.create_user(
            username='other-owner',
            password='pw',
            email='other-owner@example.com',
        )
        self.other_listing = Listing.objects.create(
            owner=self.other_owner,
            title='Other Rental',
            description='Visible listing from another owner',
            category='rentals',
            city='Irving',
            price=Decimal('1750.00'),
            bedrooms=2,
            status='active',
        )
        self.community = Community.objects.create(
            owner=self.owner,
            name='The Reserve',
            description='Modern apartments with pool and gym.',
            city='Irving',
            status='active',
            contact_email='leasing@reserve.example.com',
            community_type='apartment_complex',
        )
        self.community_floor_plan = FloorPlan.objects.create(
            community=self.community,
            name='B1',
            bedrooms=2,
            bathrooms=2,
        )
        Unit.objects.create(
            floor_plan=self.community_floor_plan,
            unit_number='201',
            price=Decimal('1700.00'),
            status='available',
        )

    def test_listing_list_hides_expired_listing(self):
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        listings = response.context['listings']
        self.assertIn(self.active_listing, listings)
        self.assertNotIn(self.expired_listing, listings)

    def test_listing_list_hides_authenticated_users_own_listings(self):
        self.client.force_login(self.owner)

        response = self.client.get('/')

        self.assertEqual(response.status_code, 200)
        listings = response.context['listings']
        self.assertNotIn(self.active_listing, listings)
        self.assertIn(self.other_listing, listings)

    def test_guided_search_post_creates_lead_preference_and_session(self):
        user = User.objects.create_user(
            username='priya',
            password='pw',
            email='priya@example.com',
            first_name='Priya',
        )
        self.client.force_login(user)

        response = self.client.post('/search/guided/', {
            'category': 'rentals',
            'city': 'Plano',
            'bedrooms': '2',
            'max_price': '2400',
            'tags': 'parking,pool',
            'available_by': '2026-05-01',
            'fmm': '1',
        })

        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith('/?'))
        lead = Lead.objects.get(email='priya@example.com', source='guided_search')
        self.assertEqual(lead.preference.city, 'Plano')
        self.assertEqual(lead.preference.bedrooms, 2)
        self.assertEqual(lead.preference.max_budget, Decimal('2400'))
        self.assertEqual(self.client.session['gs_lead_id'], lead.pk)
        self.assertTrue(GuidedSearchEvent.objects.filter(event_type='complete').exists())

    def test_guided_search_results_include_matching_communities_for_apartments(self):
        self.community.community_amenities = 'pool, gym'
        self.community.save(update_fields=['community_amenities'])

        response = self.client.get('/', {
            'category': 'rentals',
            'city': 'Irving',
            'property_type': 'apartment',
            'bedrooms': '2',
            'max_price': '1800',
            'tags': 'pool',
            'fmm': '1',
        })

        self.assertEqual(response.status_code, 200)
        self.assertIn(self.community, response.context['communities'])
        self.assertEqual(response.context['total_matches'], len(response.context['listings']) + 1)
        self.assertContains(response, 'The Reserve')
        self.assertContains(response, 'Apartment Complex')
        self.assertContains(response, 'Pool')
        self.assertContains(response, 'match')

    def test_listing_inquiry_creates_assigned_lead_and_sends_email(self):
        response = self.client.post(f'/listing/{self.active_listing.pk}/', {
            'name': 'Arjun Patel',
            'email': 'arjun@example.com',
            'phone': '5551234567',
            'message': 'I am interested in this listing.',
        }, follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(ListingInquiry.objects.count(), 1)
        lead = Lead.objects.get(email='arjun@example.com', source='inquiry')
        self.assertEqual(lead.listing, self.active_listing)
        self.assertEqual(lead.assigned_agent, self.agent)
        self.assertEqual(lead.preference.city, 'Irving')
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('New inquiry for', mail.outbox[0].subject)

    def test_community_detail_renders_and_accepts_tour_request(self):
        response = self.client.get(f'/communities/{self.community.pk}/')

        self.assertEqual(response.status_code, 200)

        response = self.client.post(f'/communities/{self.community.pk}/', {
            'name': 'Taylor Reed',
            'email': 'taylor@example.com',
            'phone': '5551112222',
            'message': 'I would like to tour this week.',
            'tour_type': 'virtual',
        }, follow=True)

        self.assertEqual(response.status_code, 200)
        lead = Lead.objects.get(email='taylor@example.com', source='inquiry')
        self.assertIsNone(lead.listing)
        self.assertEqual(lead.community, self.community)
        self.assertEqual(lead.assigned_agent, self.agent)
        self.assertEqual(lead.preference.city, 'Irving')
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('New community tour request', mail.outbox[0].subject)

    def test_log_impressions_requires_csrf(self):
        response = Client(enforce_csrf_checks=True).post(
            '/listing/impressions/',
            data='{"search_id": "", "impressions": []}',
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 403)

    def test_log_impressions_accepts_community_events(self):
        client = Client(enforce_csrf_checks=True)
        response = client.get('/')
        self.assertEqual(response.status_code, 200)
        csrf_token = response.cookies['csrftoken'].value

        response = client.post('/listing/impressions/', {
            'search_id': '',
            'impressions': [
                {'kind': 'community', 'pk': self.community.pk, 'rank': 0, 'fmm_score': None},
                {'kind': 'listing', 'pk': self.active_listing.pk, 'rank': 1, 'fmm_score': 0.75},
            ],
        }, content_type='application/json', HTTP_X_CSRFTOKEN=csrf_token)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(UserListingEvent.objects.filter(event_type='impression').count(), 2)
        self.assertTrue(UserListingEvent.objects.filter(community=self.community, listing__isnull=True).exists())
        self.assertTrue(UserListingEvent.objects.filter(listing=self.active_listing).exists())


class PartnerCsvImportTests(TestCase):
    """
    Covers the two rules that make partner ingestion safe to re-run:
    stable identity (upsert, never duplicate) and two-strike deactivation.
    """

    HEADER = ('source_listing_id,address_line,city,price,bedrooms,property_type\n')

    def setUp(self):
        self.owner = User.objects.create_user(
            username='partner-owner', password='pw', email='pm@example.com')

    def _org(self, slug='acme'):
        from partners.models import Membership, Organization
        org, created = Organization.objects.get_or_create(
            slug=slug, defaults={'name': slug.title(), 'status': 'active'})
        if created:
            Membership.objects.create(user=self.owner, organization=org, role='owner')
        return org

    def _import(self, body, **kwargs):
        from listings.services.partner_import import CsvAdapter, import_partner_inventory
        slug = kwargs.pop('partner_ref', 'acme')
        kwargs.setdefault('organization', self._org(slug))
        kwargs.setdefault('fetch_photos', False)
        return import_partner_inventory(CsvAdapter(io.StringIO(body)), **kwargs)

    def test_import_creates_listings_from_csv(self):
        result = self._import(
            self.HEADER
            + 'A-1,100 Main St,Dallas,1500,1,apartment\n'
            + 'A-2,102 Main St,Dallas,1800,2,apartment\n')

        self.assertEqual(result.created, 2)
        self.assertEqual(Listing.objects.filter(organization=self._org('acme')).count(), 2)

        listing = Listing.objects.get(source_listing_id='A-1')
        self.assertEqual(listing.price, Decimal('1500'))
        self.assertEqual(listing.source_type, 'partner_csv')
        self.assertEqual(listing.title, '1BR Apartment in Dallas')

    def test_reimport_updates_instead_of_duplicating(self):
        self._import(self.HEADER + 'A-1,100 Main St,Dallas,1500,1,apartment\n')
        result = self._import(self.HEADER + 'A-1,100 Main Street,Dallas,1595,1,apartment\n')

        self.assertEqual(result.created, 0)
        self.assertEqual(result.updated, 1)
        self.assertEqual(Listing.objects.filter(organization=self._org('acme')).count(), 1)
        # Address changed but identity held — the old bug would have made a second row.
        self.assertEqual(Listing.objects.get(source_listing_id='A-1').price, Decimal('1595'))

    def test_absent_listing_needs_two_runs_to_deactivate(self):
        both = (self.HEADER
                + 'A-1,100 Main St,Dallas,1500,1,apartment\n'
                + 'A-2,102 Main St,Dallas,1800,2,apartment\n')
        self._import(both)

        # First run without A-2: pending, still visible.
        result = self._import(self.HEADER + 'A-1,100 Main St,Dallas,1500,1,apartment\n',
                              deactivation_ceiling=0.9)
        self.assertEqual(result.pending_deactivation, 1)
        self.assertEqual(result.deactivated, 0)
        absent = Listing.objects.get(source_listing_id='A-2')
        self.assertEqual(absent.status, 'active')
        self.assertIsNotNone(absent.deactivation_pending_since)

        # Second run without A-2: now closed.
        result = self._import(self.HEADER + 'A-1,100 Main St,Dallas,1500,1,apartment\n',
                              deactivation_ceiling=0.9)
        self.assertEqual(result.deactivated, 1)
        self.assertEqual(Listing.objects.get(source_listing_id='A-2').status, 'closed')

    def test_returning_listing_clears_pending_deactivation(self):
        both = (self.HEADER
                + 'A-1,100 Main St,Dallas,1500,1,apartment\n'
                + 'A-2,102 Main St,Dallas,1800,2,apartment\n')
        self._import(both)
        self._import(self.HEADER + 'A-1,100 Main St,Dallas,1500,1,apartment\n',
                     deactivation_ceiling=0.9)
        self._import(both)

        restored = Listing.objects.get(source_listing_id='A-2')
        self.assertIsNone(restored.deactivation_pending_since)
        self.assertEqual(restored.status, 'active')

    def test_truncated_file_aborts_instead_of_mass_deactivating(self):
        rows = ''.join(
            f'A-{n},{n} Main St,Dallas,1500,1,apartment\n' for n in range(10))
        self._import(self.HEADER + rows)

        # A file with one row would retire 9 of 10 — that is a broken upload.
        result = self._import(self.HEADER + 'A-0,0 Main St,Dallas,1500,1,apartment\n')

        self.assertFalse(result.ok)
        self.assertIn('partial upload', result.aborted_reason)
        self.assertEqual(
            Listing.objects.filter(organization=self._org('acme')).exclude(status='closed').count(), 10)

    def test_bad_rows_are_rejected_without_failing_the_file(self):
        result = self._import(
            self.HEADER
            + 'A-1,100 Main St,Dallas,1500,1,apartment\n'
            + 'A-2,102 Main St,Dallas,not-a-number,2,apartment\n'
            + ',104 Main St,Dallas,1900,2,apartment\n')

        self.assertEqual(result.created, 1)
        self.assertEqual(len(result.rejections), 2)
        reasons = ' '.join(r.reason for r in result.rejections)
        self.assertIn('price', reasons)
        self.assertIn('source_listing_id is required', reasons)

    def test_missing_required_column_rejects_whole_file(self):
        result = self._import('address_line,city,price\n100 Main St,Dallas,1500\n')

        self.assertFalse(result.ok)
        self.assertIn('source_listing_id', result.rejections[0].reason)
        self.assertEqual(Listing.objects.count(), 0)

    def test_partners_do_not_deactivate_each_others_listings(self):
        self._import(self.HEADER + 'A-1,100 Main St,Dallas,1500,1,apartment\n',
                     partner_ref='acme')
        self._import(self.HEADER + 'B-1,200 Elm St,Plano,1600,1,apartment\n',
                     partner_ref='globex')

        acme = Listing.objects.get(organization=self._org('acme'))
        self.assertEqual(acme.status, 'active')
        self.assertIsNone(acme.deactivation_pending_since)

    def test_pipe_separated_tags_become_comma_separated(self):
        self._import('source_listing_id,address_line,city,price,tags\n'
                     'A-1,100 Main St,Dallas,1500,pet-friendly|parking\n')

        listing = Listing.objects.get(source_listing_id='A-1')
        self.assertEqual(listing.tags, 'pet-friendly, parking')
        self.assertEqual(listing.get_tags_list(), ['pet-friendly', 'parking'])


class PartnerCommunityImportTests(TestCase):
    """
    Units inside a managed property must import as Community -> FloorPlan -> Unit,
    because that is what renders the Community chip and the floor-plan tables.
    """

    HEADER = ('community_ref,community_name,community_city,floor_plan_name,'
              'unit_number,bedrooms,bathrooms,square_footage,price\n')

    ROWS = ('MAPLE,Maple Court,Dallas,A1 - 1 Bed,101,1,1,720,1450\n'
            'MAPLE,Maple Court,Dallas,A1 - 1 Bed,104,1,1,720,1495\n'
            'MAPLE,Maple Court,Dallas,B2 - 2 Bed,201,2,2,1040,1875\n')

    def setUp(self):
        self.owner = User.objects.create_user(
            username='pm-owner', password='pw', email='pm2@example.com')

    def _org(self, slug='acme'):
        from partners.models import Membership, Organization
        org, created = Organization.objects.get_or_create(
            slug=slug, defaults={'name': slug.title(), 'status': 'active'})
        if created:
            Membership.objects.create(user=self.owner, organization=org, role='owner')
        return org

    def _import(self, body, **kwargs):
        from listings.services.partner_import import CsvAdapter, import_partner_inventory
        slug = kwargs.pop('partner_ref', 'acme')
        kwargs.setdefault('organization', self._org(slug))
        kwargs.setdefault('fetch_photos', False)
        return import_partner_inventory(CsvAdapter(io.StringIO(body)), **kwargs)

    def test_unit_rows_build_the_community_hierarchy(self):
        result = self._import(self.HEADER + self.ROWS)

        self.assertEqual(result.communities, 1)
        self.assertEqual(result.floor_plans, 2)
        self.assertEqual(result.units, 3)

        community = Community.objects.get(name='Maple Court')
        self.assertEqual(community.managed_by, self._org('acme'))
        self.assertEqual(community.floor_plans.count(), 2)
        # These three properties drive the search card.
        self.assertEqual(community.available_unit_count, 3)
        self.assertEqual(community.price_range, (Decimal('1450'), Decimal('1875')))
        self.assertEqual(community.bedroom_types, [1, 2])

    def test_repeated_community_columns_do_not_duplicate_the_community(self):
        self._import(self.HEADER + self.ROWS)
        result = self._import(self.HEADER + self.ROWS)

        self.assertEqual(Community.objects.filter(managed_by=self._org('acme')).count(), 1)
        self.assertEqual(FloorPlan.objects.count(), 2)
        self.assertEqual(Unit.objects.count(), 3)
        self.assertEqual(result.communities, 0)   # updated, not created

    def test_absent_unit_needs_two_runs_to_withdraw(self):
        self._import(self.HEADER + self.ROWS)
        shorter = self.HEADER + ''.join(self.ROWS.splitlines(keepends=True)[:2])

        result = self._import(shorter, deactivation_ceiling=0.9)
        self.assertEqual(result.pending_deactivation, 1)
        unit = Unit.objects.get(source_unit_id='201')
        self.assertEqual(unit.status, 'available')

        result = self._import(shorter, deactivation_ceiling=0.9)
        self.assertEqual(result.deactivated, 1)
        unit.refresh_from_db()
        self.assertEqual(unit.status, 'withdrawn')

    def test_withdrawn_unit_drops_out_of_the_community_card(self):
        self._import(self.HEADER + self.ROWS)
        shorter = self.HEADER + ''.join(self.ROWS.splitlines(keepends=True)[:2])
        self._import(shorter, deactivation_ceiling=0.9)
        self._import(shorter, deactivation_ceiling=0.9)

        community = Community.objects.get(name='Maple Court')
        self.assertEqual(community.available_unit_count, 2)
        # The 2BR floor plan is gone from the chip row, and the top price with it.
        self.assertEqual(community.price_range, (Decimal('1450'), Decimal('1495')))

    def test_price_changes_update_the_existing_unit(self):
        self._import(self.HEADER + self.ROWS)
        bumped = self.ROWS.replace(',1450\n', ',1550\n')
        self._import(self.HEADER + bumped)

        self.assertEqual(Unit.objects.get(source_unit_id='101').price, Decimal('1550'))
        self.assertEqual(Unit.objects.count(), 3)

    def test_one_file_can_carry_communities_and_standalone_rentals(self):
        body = ('community_ref,community_name,community_city,floor_plan_name,unit_number,'
                'bedrooms,bathrooms,square_footage,price,source_listing_id,address_line,city\n'
                'MAPLE,Maple Court,Dallas,A1 - 1 Bed,101,1,1,720,1450,,,\n'
                ',,,,,,,,2400,SFH-1,1807 Cedar Ln,Plano\n')
        result = self._import(body)

        self.assertEqual(result.communities, 1)
        self.assertEqual(result.units, 1)
        self.assertEqual(Listing.objects.filter(organization=self._org('acme')).count(), 1)
        self.assertEqual(Listing.objects.get(source_listing_id='SFH-1').city, 'Plano')

    def test_community_row_missing_floor_plan_is_rejected(self):
        result = self._import(
            'community_ref,community_name,community_city,floor_plan_name,unit_number,bedrooms,price\n'
            'MAPLE,Maple Court,Dallas,,101,1,1450\n')

        self.assertFalse(result.ok)
        self.assertIn('floor_plan_name is required', result.rejections[0].reason)

    def test_units_from_one_partner_do_not_withdraw_anothers(self):
        self._import(self.HEADER + self.ROWS, partner_ref='acme')
        self._import('community_ref,community_name,community_city,floor_plan_name,'
                     'unit_number,bedrooms,bathrooms,square_footage,price\n'
                     'ELM,Elm Tower,Plano,C1,301,1,1,600,1300\n', partner_ref='globex')

        for unit in Unit.objects.filter(floor_plan__community__managed_by=self._org('acme')):
            self.assertEqual(unit.status, 'available')
            self.assertIsNone(unit.deactivation_pending_since)


class NearbySchoolTests(TestCase):
    """
    Covers the GreatSchools sync and the card it feeds.

    The API is never called: `_fake_response` stands in for it, so these tests
    pin our mapping and write behaviour rather than GreatSchools' uptime.
    """

    # The three schools from the reference design, deliberately supplied out of
    # display order and mixing the two field spellings the API has shipped.
    PAYLOAD = {'schools': [
        {'universal-id': 'gs-3', 'name': 'Central High School', 'level-codes': 'h',
         'gradeRange': '9-12', 'rating': 6, 'test-score-rating': 7,
         'college-readiness-rating': 6, 'student-progress-rating': 4, 'distance': 1.9},
        {'universalId': 'gs-1', 'name': 'Freedom Elementary School', 'levelCodes': 'e',
         'grade-range': 'PK-4', 'rating': 8, 'testScoreRating': 8,
         'studentProgressRating': 8, 'distance': 1.42},
        {'universal-id': 'gs-2', 'name': 'Hillwood Middle School', 'level-codes': 'm',
         'gradeRange': '7, 8', 'rating': 8, 'test-score-rating': 8,
         'student-progress-rating': 7, 'distance': 3.4},
    ]}

    def setUp(self):
        # A pre_save signal geocodes every Listing.save(), and sync_instance
        # saves. Stubbed for the whole class so these tests never call Google —
        # including on the save that stamps schools_updated.
        patcher = mock.patch('listings.services.geocoding.geocode_address',
                             return_value=None)
        patcher.start()
        self.addCleanup(patcher.stop)

        self.owner = User.objects.create_user(username='schoolowner', password='pw')
        self.listing = Listing.objects.create(
            owner=self.owner,
            title='Geocoded Rental',
            description='Has coordinates',
            category='rentals',
            price=Decimal('1500'),
            city='Keller',
            state='TX',
            status='active',
            latitude=Decimal('32.914178'),
            longitude=Decimal('-96.964342'),
        )
        cache.clear()  # the service caches per coordinate grid square

    def _sync(self, payload=None, status=200, **kwargs):
        body = self.PAYLOAD if payload is None else payload

        class _Resp:
            status_code = status

            def raise_for_status(self):
                if status >= 400:
                    raise requests.HTTPError(f'{status}')

            def json(self):
                return body

        with override_settings(GREATSCHOOLS_API_KEY='test-key'):
            with mock.patch('listings.services.greatschools.requests.get',
                            return_value=_Resp()) as get:
                result = greatschools.sync_instance(self.listing, **kwargs)
        return result, get

    def test_sync_stores_schools_and_distances(self):
        count, _ = self._sync()

        self.assertEqual(count, 3)
        self.assertEqual(School.objects.count(), 3)

        freedom = School.objects.get(gs_id='gs-1')
        self.assertEqual(freedom.name, 'Freedom Elementary School')
        self.assertEqual(freedom.grade_range, 'PK-4')
        self.assertEqual(freedom.rating, 8)
        # 1.42 from the API rounds to the one decimal place the card shows.
        link = ListingSchool.objects.get(listing=self.listing, school=freedom)
        self.assertEqual(link.distance_miles, Decimal('1.4'))

    def test_cards_read_elementary_then_middle_then_high(self):
        self._sync()
        self.assertEqual(
            [l.school.name for l in self.listing.school_cards],
            ['Freedom Elementary School', 'Hillwood Middle School', 'Central High School'],
        )

    def test_only_populated_rating_rows_are_offered(self):
        self._sync()
        elementary = School.objects.get(gs_id='gs-1')
        high = School.objects.get(gs_id='gs-3')

        # College readiness is a high-school measure — the elementary card must
        # not show an empty row for it.
        self.assertEqual([label for label, _ in elementary.rating_rows],
                         ['Test Score Rating', 'Student Progress Rating'])
        self.assertIn('College Readiness Rating', [label for label, _ in high.rating_rows])

    def test_a_failed_lookup_leaves_stored_schools_alone(self):
        self._sync()
        self.assertEqual(self.listing.nearby_schools.count(), 3)

        cache.clear()
        count, _ = self._sync(status=500, force=True)

        # A quota error or outage must not read as "this address has no schools".
        self.assertIsNone(count)
        self.assertEqual(self.listing.nearby_schools.count(), 3)

    def test_a_school_that_leaves_the_radius_is_unlinked(self):
        self._sync()
        cache.clear()

        shrunk = {'schools': [self.PAYLOAD['schools'][1]]}  # elementary only
        count, _ = self._sync(payload=shrunk, force=True)

        self.assertEqual(count, 1)
        self.assertEqual([l.school.gs_id for l in self.listing.school_cards], ['gs-1'])
        # The School rows survive — another listing may still be near them.
        self.assertEqual(School.objects.count(), 3)

    def test_fresh_listings_are_not_refetched_without_force(self):
        self._sync()
        cache.clear()

        count, get = self._sync()
        self.assertIsNone(count)
        get.assert_not_called()

    def test_repeat_sync_updates_rather_than_duplicates(self):
        self._sync()
        cache.clear()

        rerated = copy.deepcopy(self.PAYLOAD)
        rerated['schools'][0]['rating'] = 9  # GreatSchools re-rates Central High
        self._sync(payload=rerated, force=True)

        self.assertEqual(School.objects.count(), 3)
        self.assertEqual(ListingSchool.objects.filter(listing=self.listing).count(), 3)
        self.assertEqual(School.objects.get(gs_id='gs-3').rating, 9)

    def test_rows_without_an_id_are_dropped(self):
        # Storing these would create a duplicate School on every refresh.
        count, _ = self._sync(payload={'schools': [{'name': 'Nameless School', 'rating': 5}]})
        self.assertEqual(count, 0)
        self.assertEqual(School.objects.count(), 0)

    def test_no_api_key_means_no_call_and_no_schools(self):
        with override_settings(GREATSCHOOLS_API_KEY=''):
            with mock.patch('listings.services.greatschools.requests.get') as get:
                count = greatschools.sync_instance(self.listing)

        get.assert_not_called()
        self.assertIsNone(count)
        self.assertEqual(self.listing.nearby_schools.count(), 0)

    def test_ungeocoded_listing_is_skipped(self):
        bare = Listing.objects.create(
            owner=self.owner, title='No coords', description='x',
            category='rentals', price=Decimal('900'), city='Keller', status='active',
        )
        with override_settings(GREATSCHOOLS_API_KEY='test-key'):
            with mock.patch('listings.services.greatschools.requests.get') as get:
                self.assertIsNone(greatschools.sync_instance(bare))
        get.assert_not_called()

    def test_nearby_listings_share_one_api_call(self):
        """Units in one community must not cost one call each."""
        self._sync()
        # ~20cm away: the same grid square, so the cached response should serve it.
        twin = Listing.objects.create(
            owner=self.owner, title='Same block', description='x', category='rentals',
            price=Decimal('1600'), city='Keller', status='active',
            latitude=Decimal('32.914180'), longitude=Decimal('-96.964340'),
        )
        with override_settings(GREATSCHOOLS_API_KEY='test-key'):
            with mock.patch('listings.services.greatschools.requests.get') as get:
                greatschools.sync_instance(twin)
        get.assert_not_called()
        self.assertEqual(twin.nearby_schools.count(), 3)

    def test_detail_page_renders_the_card(self):
        self._sync()
        response = Client().get(reverse('listing_detail', args=[self.listing.pk]))
        body = response.content.decode()

        self.assertContains(response, 'Nearby schools in Keller')
        self.assertContains(response, 'Freedom Elementary School')
        self.assertContains(response, 'Grades 9-12')
        # Attribution is a licence condition of showing the rating.
        self.assertIn('GreatSchools', body)
        # High school only, so exactly one such row on the page.
        self.assertEqual(body.count('College Readiness Rating'), 1)

    def test_card_is_absent_when_no_schools_are_stored(self):
        response = Client().get(reverse('listing_detail', args=[self.listing.pk]))
        self.assertNotContains(response, 'Nearby schools')

    def test_rating_colors_band_the_way_the_design_does(self):
        self.assertEqual(School(rating=8).rating_color, '#2b7c9e')   # blue
        self.assertEqual(School(rating=6).rating_color, '#4c8c3f')   # green
        self.assertEqual(School(rating=2).rating_color, '#c0642a')   # orange
        self.assertEqual(School(rating=None).rating_color, '#6b7280')  # unrated

    def test_multi_level_school_sorts_with_its_lowest_level(self):
        # A K-8 campus belongs where a parent looking for an elementary school
        # would scan, not after the middle schools.
        self.assertEqual(School.rank_for_levels('e,m'), School.rank_for_levels('e'))


class NearestDowntownTests(TestCase):
    """Downtown matching is local maths over a curated table — no API involved."""

    def setUp(self):
        patcher = mock.patch('listings.services.geocoding.geocode_address', return_value=None)
        patcher.start()
        self.addCleanup(patcher.stop)

        self.owner = User.objects.create_user(username='dtowner', password='pw')
        self.dallas = Downtown.objects.create(
            name='Downtown Dallas', city='Dallas', state='TX',
            latitude=Decimal('32.7767'), longitude=Decimal('-96.7970'))
        self.fort_worth = Downtown.objects.create(
            name='Downtown Fort Worth', city='Fort Worth', state='TX',
            latitude=Decimal('32.7555'), longitude=Decimal('-97.3308'))

    def _listing(self, lat, lng, **kwargs):
        return Listing.objects.create(
            owner=self.owner, title='L', description='x', category='rentals',
            price=Decimal('1500'), city=kwargs.pop('city', 'Dallas'),
            status='active', latitude=Decimal(str(lat)), longitude=Decimal(str(lng)), **kwargs)

    def test_haversine_matches_a_known_distance(self):
        # Dallas to Fort Worth city centres is a shade over 30 miles.
        miles = distance.haversine_miles(32.7767, -96.7970, 32.7555, -97.3308)
        self.assertAlmostEqual(miles, 31.0, delta=0.5)

    def test_haversine_returns_none_on_missing_coordinates(self):
        self.assertIsNone(distance.haversine_miles(None, -96.79, 32.77, -96.79))
        self.assertIsNone(distance.haversine_miles(32.77, -96.79, 32.77, None))

    def test_nearest_downtown_can_be_another_city(self):
        # A listing in west Irving is nearer Fort Worth than its own city hall.
        # Ignoring city boundaries is the point — this is a commute cue.
        listing = self._listing(32.76, -97.20, city='Irving')
        downtowns.assign_instance(listing)
        self.assertEqual(listing.nearest_downtown, self.fort_worth)

    def test_assign_sets_distance_to_one_decimal(self):
        listing = self._listing(32.7767, -96.7970)
        self.assertTrue(downtowns.assign_instance(listing))
        self.assertEqual(listing.nearest_downtown, self.dallas)
        self.assertEqual(listing.downtown_distance_miles, 0.0)

    def test_inactive_downtowns_are_not_matched(self):
        Downtown.objects.update(is_active=False)
        listing = self._listing(32.7767, -96.7970)
        self.assertFalse(downtowns.assign_instance(listing))
        self.assertIsNone(listing.nearest_downtown)

    def test_a_listing_that_stops_matching_is_cleared(self):
        listing = self._listing(32.7767, -96.7970)
        downtowns.assign_instance(listing)
        listing.save()

        Downtown.objects.update(is_active=False)
        downtowns.assign_instance(listing)

        # A stale downtown left behind would misreport the commute.
        self.assertIsNone(listing.nearest_downtown)
        self.assertIsNone(listing.downtown_distance_miles)

    def test_ungeocoded_listing_matches_nothing(self):
        bare = Listing.objects.create(
            owner=self.owner, title='No coords', description='x', category='rentals',
            price=Decimal('900'), city='Dallas', status='active')
        self.assertFalse(downtowns.assign_instance(bare))

    def test_seed_command_is_idempotent(self):
        call_command('seed_downtowns', verbosity=0)
        first = Downtown.objects.count()
        call_command('seed_downtowns', verbosity=0)
        self.assertEqual(Downtown.objects.count(), first)

    def test_missing_only_skips_already_assigned_rows(self):
        """The deploy runs this on every boot — it must be a no-op once settled."""
        assigned = self._listing(32.7767, -96.7970)
        downtowns.assign_instance(assigned)
        assigned.save()
        unassigned = self._listing(32.7555, -97.3308)

        call_command('assign_downtowns', '--missing-only', verbosity=0)

        unassigned.refresh_from_db()
        self.assertEqual(unassigned.nearest_downtown, self.fort_worth)
        # Re-running changes nothing further.
        call_command('assign_downtowns', '--missing-only', verbosity=0)
        self.assertEqual(Listing.objects.filter(nearest_downtown__isnull=True).count(), 0)

    def test_assign_does_not_trigger_the_geocoding_signal(self):
        """
        bulk_update, not save(). This command runs on every container boot, and
        save() would fire pre_save -> geocode_on_save -> a Google call for any
        row whose address drifted from geocoded_address.
        """
        listing = self._listing(32.7767, -96.7970)
        Listing.objects.filter(pk=listing.pk).update(geocoded_address='stale mismatch')

        with mock.patch('listings.services.geocoding.geocode_address') as geo:
            call_command('assign_downtowns', verbosity=0)

        geo.assert_not_called()
        listing.refresh_from_db()
        self.assertEqual(listing.nearest_downtown, self.dallas)

    def test_detail_page_shows_the_downtown_row(self):
        listing = self._listing(32.7767, -96.7970)
        downtowns.assign_instance(listing)
        listing.save()

        response = Client().get(reverse('listing_detail', args=[listing.pk]))
        self.assertContains(response, 'Neighborhood')
        self.assertContains(response, 'Downtown Dallas')
        self.assertContains(response, 'nearest downtown')


class NearbyGroceryTests(TestCase):
    """
    Covers the Places sync and, above all, what it refuses to store.

    The API is never called — `_sync` stands in for it.
    """

    def _place(self, place_id, name, lat, lng, types=('supermarket',)):
        return {'id': place_id, 'displayName': {'text': name}, 'types': list(types),
                'formattedAddress': f'{name}, TX', 'location': {'latitude': lat, 'longitude': lng}}

    def setUp(self):
        patcher = mock.patch('listings.services.geocoding.geocode_address', return_value=None)
        patcher.start()
        self.addCleanup(patcher.stop)

        self.owner = User.objects.create_user(username='groceryowner', password='pw')
        self.listing = Listing.objects.create(
            owner=self.owner, title='Geocoded Rental', description='x', category='rentals',
            price=Decimal('1500'), city='Keller', state='TX', status='active',
            latitude=Decimal('32.9346'), longitude=Decimal('-97.2289'))
        cache.clear()

    def _sync(self, places, status=200, **kwargs):
        class _Resp:
            status_code = status

            def raise_for_status(self):
                if status >= 400:
                    raise requests.HTTPError(f'{status}')

            def json(self):
                return {'places': places}

        with override_settings(GOOGLE_PLACES_API_KEY='test-key'):
            with mock.patch('listings.services.groceries.requests.post',
                            return_value=_Resp()) as post:
                result = groceries.sync_instance(self.listing, **kwargs)
        return result, post

    # ── the chain whitelist ───────────────────────────────────────────────

    def test_known_chains_resolve_to_canonical_names(self):
        for raw, expected in [
            ('Walmart Supercenter', 'Walmart'),
            ('Walmart Neighborhood Market', 'Walmart'),
            ("Sam's Club", "Sam's Club"),
            ('Costco Wholesale', 'Costco'),
            ('Kroger', 'Kroger'),
            ('H-E-B plus!', 'H-E-B'),
            ('HEB', 'H-E-B'),
            ('Sprouts Farmers Market', 'Sprouts'),
        ]:
            self.assertEqual(groceries.match_chain(raw), expected, raw)

    def test_petrol_stations_are_never_groceries(self):
        for name in ('Shell', '7-Eleven', 'QuikTrip', 'RaceTrac', 'Exxon', 'Buc-ee’s'):
            self.assertIsNone(groceries.match_chain(name), name)

    def test_chain_branded_fuel_and_pharmacy_outlets_are_excluded(self):
        # The subtle case: these carry a real chain name but are not a grocery
        # run, and Places returns them as separate places in the same car park.
        for name in ("Sam's Club Gas", 'Costco Gasoline', 'Kroger Fuel Center',
                     'Walmart Pharmacy', 'Walmart Auto Care Center', 'Costco Tire Center'):
            self.assertIsNone(groceries.match_chain(name), name)

    def test_a_place_typed_as_a_gas_station_is_dropped(self):
        # Belt and braces: the type check catches what the name check misses.
        count, _ = self._sync([self._place('p1', 'Kroger', 32.93, -97.22,
                                           types=('gas_station', 'supermarket'))])
        self.assertEqual(count, 0)
        self.assertEqual(GroceryStore.objects.count(), 0)

    def test_unknown_independents_are_dropped(self):
        count, _ = self._sync([self._place('p1', 'Bobs Corner Store', 32.93, -97.22)])
        self.assertEqual(count, 0)

    # ── sync behaviour ────────────────────────────────────────────────────

    def test_sync_stores_chains_with_distances(self):
        count, _ = self._sync([
            self._place('p1', 'Kroger', 32.9400, -97.2300),
            self._place('p2', 'Costco Wholesale', 32.9800, -97.2800),
        ])
        self.assertEqual(count, 2)
        self.assertEqual(
            [(l.store.chain, float(l.distance_miles)) for l in self.listing.grocery_cards],
            sorted([(l.store.chain, float(l.distance_miles)) for l in self.listing.grocery_cards],
                   key=lambda p: p[1]))
        self.assertEqual(self.listing.grocery_cards.first().store.chain, 'Kroger')

    def test_only_the_nearest_branch_of_a_chain_is_kept(self):
        # Three Walmarts must not fill the card.
        count, _ = self._sync([
            self._place('far', 'Walmart Supercenter', 33.10, -97.40),
            self._place('near', 'Walmart Neighborhood Market', 32.9350, -97.2290),
            self._place('mid', 'Walmart Supercenter', 33.00, -97.30),
        ])
        self.assertEqual(count, 1)
        self.assertEqual(self.listing.grocery_cards.first().store.place_id, 'near')

    def test_chain_count_is_capped(self):
        places = [self._place(f'p{i}', chain, 32.93 + i / 100, -97.22)
                  for i, chain in enumerate(['Kroger', 'Costco Wholesale', 'Target', 'Aldi',
                                             'Tom Thumb', 'Whole Foods Market', 'Publix'])]
        count, _ = self._sync(places, limit=3)
        self.assertEqual(count, 3)

    def test_a_failed_lookup_leaves_stored_stores_alone(self):
        self._sync([self._place('p1', 'Kroger', 32.94, -97.23)])
        cache.clear()

        count, _ = self._sync([], status=500, force=True)

        self.assertIsNone(count)
        self.assertEqual(self.listing.nearby_groceries.count(), 1)

    def test_a_store_that_closes_is_unlinked(self):
        self._sync([self._place('p1', 'Kroger', 32.94, -97.23),
                    self._place('p2', 'Aldi', 32.95, -97.24)])
        cache.clear()

        count, _ = self._sync([self._place('p1', 'Kroger', 32.94, -97.23)], force=True)

        self.assertEqual(count, 1)
        self.assertEqual([l.store.chain for l in self.listing.grocery_cards], ['Kroger'])

    def test_fresh_listings_are_not_refetched_without_force(self):
        self._sync([self._place('p1', 'Kroger', 32.94, -97.23)])
        cache.clear()

        count, post = self._sync([self._place('p1', 'Kroger', 32.94, -97.23)])
        self.assertIsNone(count)
        post.assert_not_called()

    def test_nearby_listings_share_one_api_call(self):
        self._sync([self._place('p1', 'Kroger', 32.94, -97.23)])
        twin = Listing.objects.create(
            owner=self.owner, title='Same block', description='x', category='rentals',
            price=Decimal('1600'), city='Keller', status='active',
            latitude=Decimal('32.934610'), longitude=Decimal('-97.228870'))

        with override_settings(GOOGLE_PLACES_API_KEY='test-key'):
            with mock.patch('listings.services.groceries.requests.post') as post:
                groceries.sync_instance(twin)

        post.assert_not_called()
        self.assertEqual(twin.nearby_groceries.count(), 1)

    def test_no_api_key_means_no_call(self):
        with override_settings(GOOGLE_PLACES_API_KEY='', GOOGLE_GEOCODING_API_KEY='',
                               GOOGLE_MAPS_API_KEY=''):
            with mock.patch('listings.services.groceries.requests.post') as post:
                count = groceries.sync_instance(self.listing)

        post.assert_not_called()
        self.assertIsNone(count)

    def test_field_mask_requests_only_stored_fields(self):
        # Places (New) bills by requested fields — an over-broad mask silently
        # moves every call to a dearer SKU.
        _, post = self._sync([self._place('p1', 'Kroger', 32.94, -97.23)])
        mask = post.call_args.kwargs['headers']['X-Goog-FieldMask']
        self.assertNotIn('places.rating', mask)
        self.assertNotIn('*', mask)

    def test_detail_page_shows_grocery_rows(self):
        self._sync([self._place('p1', 'Kroger', 32.94, -97.23),
                    self._place('p2', 'Costco Wholesale', 32.98, -97.28)])

        response = Client().get(reverse('listing_detail', args=[self.listing.pk]))
        self.assertContains(response, 'Grocery stores nearby')
        self.assertContains(response, 'Kroger')
        self.assertContains(response, 'Costco')

    def test_card_is_absent_when_nothing_is_stored(self):
        response = Client().get(reverse('listing_detail', args=[self.listing.pk]))
        self.assertNotContains(response, 'Grocery stores nearby')
        self.assertNotContains(response, 'Neighborhood')


class DriveTimeTests(TestCase):
    """
    Covers the Routes matrix sync.

    The API is never called — `_sync` stands in for it. The behaviour most worth
    pinning is that results are matched by index, not by position.
    """

    def setUp(self):
        patcher = mock.patch('listings.services.geocoding.geocode_address', return_value=None)
        patcher.start()
        self.addCleanup(patcher.stop)

        self.owner = User.objects.create_user(username='driveowner', password='pw')
        self.downtown = Downtown.objects.create(
            name='Downtown Las Colinas', city='Irving', state='TX',
            latitude=Decimal('32.8626'), longitude=Decimal('-96.9433'))
        self.listing = Listing.objects.create(
            owner=self.owner, title='Rental', description='x', category='rentals',
            price=Decimal('1500'), city='Irving', state='TX', status='active',
            latitude=Decimal('32.9346'), longitude=Decimal('-97.2289'),
            nearest_downtown=self.downtown, downtown_distance_miles=Decimal('3.8'))

    def _store(self, place_id, chain, miles, lat=32.94, lng=-97.23):
        store = GroceryStore.objects.create(place_id=place_id, chain=chain, name=chain,
                                            latitude=lat, longitude=lng)
        return ListingGroceryStore.objects.create(
            listing=self.listing, store=store, distance_miles=Decimal(str(miles)))

    def _sync(self, elements, status=200, **kwargs):
        class _Resp:
            status_code = status

            def raise_for_status(self):
                if status >= 400:
                    raise requests.HTTPError(f'{status}')

            def json(self):
                return elements

        with override_settings(GOOGLE_ROUTES_API_KEY='test-key'):
            with mock.patch('listings.services.drivetime.requests.post',
                            return_value=_Resp()) as post:
                result = drivetime.sync_instance(self.listing, **kwargs)
        return result, post

    def test_downtown_and_groceries_share_one_api_call(self):
        """The whole point: one request, not one per destination."""
        self._store('p1', 'Kroger', 0.4)
        self._store('p2', 'Costco', 4.3)

        count, post = self._sync([
            {'originIndex': 0, 'destinationIndex': 0, 'condition': 'ROUTE_EXISTS', 'duration': '540s'},
            {'originIndex': 0, 'destinationIndex': 1, 'condition': 'ROUTE_EXISTS', 'duration': '180s'},
            {'originIndex': 0, 'destinationIndex': 2, 'condition': 'ROUTE_EXISTS', 'duration': '600s'},
        ])

        self.assertEqual(post.call_count, 1)
        self.assertEqual(count, 3)
        self.listing.refresh_from_db()
        self.assertEqual(self.listing.downtown_drive_minutes, 9)

    def test_results_are_matched_by_index_not_position(self):
        # The matrix response is a stream and arrives out of order. Zipping by
        # position here would silently give the downtown the Kroger's time.
        kroger = self._store('p1', 'Kroger', 0.4)
        costco = self._store('p2', 'Costco', 4.3)

        self._sync([
            {'originIndex': 0, 'destinationIndex': 2, 'condition': 'ROUTE_EXISTS', 'duration': '600s'},
            {'originIndex': 0, 'destinationIndex': 0, 'condition': 'ROUTE_EXISTS', 'duration': '540s'},
            {'originIndex': 0, 'destinationIndex': 1, 'condition': 'ROUTE_EXISTS', 'duration': '180s'},
        ])

        self.listing.refresh_from_db()
        kroger.refresh_from_db()
        costco.refresh_from_db()
        self.assertEqual(self.listing.downtown_drive_minutes, 9)   # slot 0
        self.assertEqual(kroger.drive_minutes, 3)                  # slot 1
        self.assertEqual(costco.drive_minutes, 10)                 # slot 2

    def test_traffic_unaware_is_requested(self):
        # Traffic-aware is a dearer SKU and would be stale by render time.
        self._store('p1', 'Kroger', 0.4)
        _, post = self._sync([])
        self.assertEqual(post.call_args.kwargs['json']['routingPreference'], 'TRAFFIC_UNAWARE')
        self.assertEqual(post.call_args.kwargs['json']['travelMode'], 'DRIVE')

    def test_one_origin_many_destinations(self):
        self._store('p1', 'Kroger', 0.4)
        self._store('p2', 'Costco', 4.3)
        _, post = self._sync([])
        body = post.call_args.kwargs['json']
        self.assertEqual(len(body['origins']), 1)
        self.assertEqual(len(body['destinations']), 3)  # downtown + 2 stores

    def test_unroutable_destinations_are_skipped(self):
        kroger = self._store('p1', 'Kroger', 0.4)
        count, _ = self._sync([
            {'originIndex': 0, 'destinationIndex': 0, 'condition': 'ROUTE_NOT_FOUND'},
            {'originIndex': 0, 'destinationIndex': 1, 'condition': 'ROUTE_EXISTS', 'duration': '180s'},
        ])
        self.listing.refresh_from_db()
        kroger.refresh_from_db()
        self.assertEqual(count, 1)
        self.assertIsNone(self.listing.downtown_drive_minutes)
        self.assertEqual(kroger.drive_minutes, 3)

    def test_sub_minute_hops_round_to_one_minute(self):
        kroger = self._store('p1', 'Kroger', 0.1)
        self._sync([{'originIndex': 0, 'destinationIndex': 1,
                     'condition': 'ROUTE_EXISTS', 'duration': '25s'}])
        kroger.refresh_from_db()
        self.assertEqual(kroger.drive_minutes, 1)  # never "0 min"

    def test_a_failed_lookup_leaves_stored_times_alone(self):
        self._store('p1', 'Kroger', 0.4)
        self._sync([{'originIndex': 0, 'destinationIndex': 0,
                     'condition': 'ROUTE_EXISTS', 'duration': '540s'}])

        count, _ = self._sync([], status=500, force=True)

        self.assertIsNone(count)
        self.listing.refresh_from_db()
        self.assertEqual(self.listing.downtown_drive_minutes, 9)

    def test_listing_with_nothing_to_measure_makes_no_call(self):
        bare = Listing.objects.create(
            owner=self.owner, title='No proximity', description='x', category='rentals',
            price=Decimal('900'), city='Irving', status='active',
            latitude=Decimal('32.9'), longitude=Decimal('-97.2'))
        with override_settings(GOOGLE_ROUTES_API_KEY='test-key'):
            with mock.patch('listings.services.drivetime.requests.post') as post:
                self.assertIsNone(drivetime.sync_instance(bare))
        post.assert_not_called()

    def test_no_api_key_means_no_call(self):
        self._store('p1', 'Kroger', 0.4)
        with override_settings(GOOGLE_ROUTES_API_KEY='', GOOGLE_PLACES_API_KEY='',
                               GOOGLE_GEOCODING_API_KEY='', GOOGLE_MAPS_API_KEY=''):
            with mock.patch('listings.services.drivetime.requests.post') as post:
                self.assertIsNone(drivetime.sync_instance(self.listing))
        post.assert_not_called()

    def test_detail_page_shows_drive_times(self):
        self._store('p1', 'Kroger', 0.4)
        self._sync([
            {'originIndex': 0, 'destinationIndex': 0, 'condition': 'ROUTE_EXISTS', 'duration': '540s'},
            {'originIndex': 0, 'destinationIndex': 1, 'condition': 'ROUTE_EXISTS', 'duration': '180s'},
        ])

        response = Client().get(reverse('listing_detail', args=[self.listing.pk]))
        self.assertContains(response, '9 min drive')
        self.assertContains(response, '3 min')
        self.assertContains(response, 'drive times in typical traffic')

    def test_footnote_omits_drive_wording_when_absent(self):
        self._store('p1', 'Kroger', 0.4)
        response = Client().get(reverse('listing_detail', args=[self.listing.pk]))
        self.assertNotContains(response, 'drive times in typical traffic')
        self.assertContains(response, 'Straight-line distance')
