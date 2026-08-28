import copy
import io
import re
from datetime import date, timedelta
from decimal import Decimal
from unittest import mock

import requests
from django.contrib.auth.models import User
from django.core import mail
from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from django.core.management import call_command

from listings.models import (MODE_BADGE_COLORS, Community, Downtown, FloorPlan, GroceryStore,
                             GuidedSearchEvent, Listing, ListingGroceryStore, ListingInquiry,
                             ListingSchool, ListingTransitStation, School, StationRoute,
                             TransitAgency, TransitRoute, TransitStation, Unit, UserListingEvent)
from listings.services import (commute_score, distance, downtowns, drivetime, greatschools,
                               groceries, gtfs, transit)
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
            {'originIndex': 0, 'destinationIndex': 0, 'condition': 'ROUTE_EXISTS', 'duration': '540s', 'distanceMeters': 8047},
            {'originIndex': 0, 'destinationIndex': 1, 'condition': 'ROUTE_EXISTS', 'duration': '180s', 'distanceMeters': 1127},
            {'originIndex': 0, 'destinationIndex': 2, 'condition': 'ROUTE_EXISTS', 'duration': '600s', 'distanceMeters': 9656},
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

    def test_road_distance_is_stored_and_preferred_over_straight_line(self):
        """
        The card must not mix measurements: showing a straight-line mileage
        beside a driving time reads as one number and is two.
        """
        kroger = self._store('p1', 'Kroger', 0.4)   # 0.4 straight-line

        self._sync([
            {'originIndex': 0, 'destinationIndex': 0, 'condition': 'ROUTE_EXISTS',
             'duration': '540s', 'distanceMeters': 8047},   # 5.0 road miles
            {'originIndex': 0, 'destinationIndex': 1, 'condition': 'ROUTE_EXISTS',
             'duration': '180s', 'distanceMeters': 1127},   # 0.7 road miles
        ])

        self.listing.refresh_from_db()
        kroger.refresh_from_db()
        # Straight-line values are preserved — they drive ranking and ordering.
        self.assertEqual(kroger.distance_miles, Decimal('0.4'))
        self.assertEqual(kroger.drive_miles, Decimal('0.7'))
        self.assertEqual(kroger.display_miles, Decimal('0.7'))
        self.assertEqual(self.listing.downtown_drive_miles, Decimal('5.0'))
        self.assertEqual(self.listing.downtown_display_miles, Decimal('5.0'))

    def test_display_falls_back_to_straight_line_without_a_route(self):
        kroger = self._store('p1', 'Kroger', 0.4)
        self._sync([{'originIndex': 0, 'destinationIndex': 1,
                     'condition': 'ROUTE_NOT_FOUND'}])
        kroger.refresh_from_db()
        self.assertIsNone(kroger.drive_miles)
        self.assertEqual(kroger.display_miles, Decimal('0.4'))

    def test_distance_is_requested_in_the_field_mask(self):
        self._store('p1', 'Kroger', 0.4)
        _, post = self._sync([])
        mask = post.call_args.kwargs['headers']['X-Goog-FieldMask']
        self.assertIn('distanceMeters', mask)

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
        self.assertContains(response, 'Driving distance and time in typical traffic')
        self.assertNotContains(response, 'Straight-line distance')

    def test_footnote_omits_drive_wording_when_absent(self):
        self._store('p1', 'Kroger', 0.4)
        response = Client().get(reverse('listing_detail', args=[self.listing.pk]))
        self.assertNotContains(response, 'Driving distance and time')
        self.assertContains(response, 'Straight-line distance')


class TemplateRenderHygieneTests(TestCase):
    """
    Guards against template syntax leaking into rendered pages.

    Motivated by a real escape: a multi-line `{# ... #}` comment in base.html.
    That form is single-line only, so Django never treated it as a comment and
    the text rendered on every page — the browser hoists stray text out of
    <head> into the visible body. Assertions on specific tags all passed while
    the site displayed the comment, so this checks for absence, not presence.
    """

    # Any of these surviving into output means a tag or comment did not parse.
    LEAK_MARKERS = ('{#', '#}', '{%', '%}', '{{', '}}')

    def setUp(self):
        patcher = mock.patch('listings.services.geocoding.geocode_address', return_value=None)
        patcher.start()
        self.addCleanup(patcher.stop)

        self.owner = User.objects.create_user(username='hygiene', password='pw')
        self.listing = Listing.objects.create(
            owner=self.owner, title='Rental', description='x', category='rentals',
            price=Decimal('1200'), city='Irving', state='TX', status='active')

    def _pages(self):
        return [
            reverse('home'),
            reverse('listing_list'),
            reverse('listing_detail', args=[self.listing.pk]),
        ]

    def test_no_template_syntax_leaks_into_any_page(self):
        for path in self._pages():
            body = Client().get(path).content.decode()
            for marker in self.LEAK_MARKERS:
                self.assertNotIn(
                    marker, body,
                    f'{path} leaked template syntax {marker!r} into the response')

    def test_head_contains_no_stray_text(self):
        """
        Text directly inside <head> is the symptom users actually see, because
        browsers move it into the body. Only the <title> and inline CSS/JS are
        legitimate.
        """
        body = Client().get(reverse('home')).content.decode()
        head = body[body.find('<head>'):body.find('</head>')]

        # Drop the elements whose text content is meant to be there.
        for tag in ('title', 'style', 'script'):
            head = re.sub(rf'<{tag}\b.*?</{tag}>', '', head, flags=re.S)

        stray = re.sub(r'<[^>]+>', '', head).strip()
        self.assertEqual(stray, '', f'stray text in <head>: {stray[:200]!r}')

    def test_title_and_description_are_within_search_limits(self):
        body = Client().get(reverse('home')).content.decode()
        title = re.search(r'<title>(.*?)</title>', body, re.S).group(1).strip()
        desc = re.search(r'<meta name="description" content="(.*?)">', body, re.S).group(1).strip()

        self.assertIn('Dallas', title)
        # Google truncates past roughly these lengths.
        self.assertLessEqual(len(title), 60, f'title too long: {title!r}')
        self.assertLessEqual(len(desc), 160, f'description too long: {desc!r}')

    def test_favicon_is_served_from_the_site_root(self):
        # Crawlers probe /favicon.ico directly and ignore the <link> tags.
        response = Client().get('/favicon.ico')
        self.assertIn(response.status_code, (301, 302))
        self.assertIn('favicon', response.headers['Location'])


def _gtfs_zip(*, calendar=None, calendar_dates=None, routes=None,
              stops=None, trips=None, stop_times=None, feed_info=True):
    """
    Build a GTFS zip in memory.

    A real zip rather than a mocked parser: the parser's whole job is tolerating
    the shapes agencies actually publish, so a test that stubbed it out would
    pin nothing worth pinning.
    """
    files = {
        'agency.txt': 'agency_id,agency_name\n1,TEST TRANSIT\n',
        'routes.txt': routes if routes is not None else '',
        'stops.txt': stops if stops is not None else '',
        'trips.txt': trips if trips is not None else '',
        'stop_times.txt': stop_times if stop_times is not None else '',
    }
    if calendar is not None:
        files['calendar.txt'] = calendar
    if calendar_dates is not None:
        files['calendar_dates.txt'] = calendar_dates
    if feed_info:
        files['feed_info.txt'] = ('feed_publisher_name,feed_lang,feed_version\n'
                                  'TEST,en,v1\n')

    buf = io.BytesIO()
    import zipfile
    with zipfile.ZipFile(buf, 'w') as zf:
        for name, body in files.items():
            zf.writestr(name, body)
    return buf.getvalue()


def _stop_times(pairs):
    """`pairs` is [(trip_id, stop_id, n_calls)] → a stop_times.txt body."""
    rows = ['trip_id,arrival_time,departure_time,stop_id,stop_sequence']
    seq = 0
    for trip_id, stop_id, n in pairs:
        for _ in range(n):
            seq += 1
            rows.append(f'{trip_id},08:00:00,08:00:00,{stop_id},{seq}')
    return '\n'.join(rows) + '\n'


class GtfsParsingTests(TestCase):
    """
    Covers services.gtfs — the shapes real agency feeds actually ship in.

    Nothing here downloads anything: each test builds the zip it needs.
    """

    ROUTES = (
        'route_id,route_short_name,route_long_name,route_type,route_color,route_text_color\n'
        'R1,RED,RED LINE,0,FD3E3E,FFFFFF\n'          # light rail
        'B1,101,MAIN STREET,3,,\n'                   # frequent bus
        'B2,102,QUIET LANE,3,,\n'                    # infrequent bus
        'F1,900,FERRY,4,,\n'                         # unmappable route_type
    )
    STOPS = (
        'stop_id,stop_name,stop_lat,stop_lon\n'
        'S1,12TH STREET STATION,32.800000,-96.800000\n'
        'S2,MAIN @ 1ST,32.810000,-96.810000\n'
        'S3,QUIET @ 2ND,32.820000,-96.820000\n'
        'S4,EAST TEX YARD LIMIT,32.830000,-96.830000\n'
        'S5,FERRY DOCK,32.840000,-96.840000\n'
    )
    TRIPS = ('route_id,service_id,trip_id\n'
             'R1,WK,t_rail\nB1,WK,t_busy\nB2,WK,t_quiet\nF1,WK,t_ferry\n')
    # 80 calls clears FREQUENT_TRIPS_PER_WEEKDAY (60); 10 does not.
    TIMES = _stop_times([('t_rail', 'S1', 12), ('t_rail', 'S4', 12),
                         ('t_busy', 'S2', 80), ('t_quiet', 'S3', 10),
                         ('t_ferry', 'S5', 40)])
    CALENDAR = ('service_id,monday,tuesday,wednesday,thursday,friday,'
                'saturday,sunday,start_date,end_date\n'
                'WK,1,1,1,1,1,0,0,20260101,20261231\n')

    def _parse(self, **kwargs):
        kwargs.setdefault('routes', self.ROUTES)
        kwargs.setdefault('stops', self.STOPS)
        kwargs.setdefault('trips', self.TRIPS)
        kwargs.setdefault('stop_times', self.TIMES)
        kwargs.setdefault('calendar', self.CALENDAR)
        return gtfs.parse_feed(_gtfs_zip(**kwargs))

    def test_keeps_every_served_stop_and_flags_the_frequent_ones(self):
        """
        Frequency labels a stop, it does not exclude one.

        The card gives rail and bus separate sections, so a thin bus stop no
        longer displaces a rail station and there is no reason to hide it.
        Valley Ranch forced this: its only service is two Irving circulators at
        ~32 trips a day, so the listing showed no bus at all rather than
        "every ~25 min".
        """
        feed = self._parse()
        by_name = {s.name: s for s in feed.stations}

        self.assertIn('12th Street Station', by_name)  # rail, kept regardless
        self.assertIn('Main @ 1st', by_name)           # 80 trips
        self.assertIn('Quiet @ 2nd', by_name)          # 10 trips — kept, flagged
        # A yard limit is timed through but nobody boards there.
        self.assertNotIn('East TEX Yard Limit', by_name)
        self.assertNotIn('Ferry Dock', by_name)        # route_type 4 is unmapped

        self.assertGreaterEqual(by_name['Main @ 1st'].trips_per_weekday,
                                gtfs.FREQUENT_TRIPS_PER_WEEKDAY)
        self.assertLess(by_name['Quiet @ 2nd'].trips_per_weekday,
                        gtfs.FREQUENT_TRIPS_PER_WEEKDAY)

    def test_drops_a_stop_with_no_weekday_service(self):
        """A stop nothing calls at on a weekday is not somewhere you can go."""
        feed = self._parse(
            calendar='service_id,monday,tuesday,wednesday,thursday,friday,'
                     'saturday,sunday,start_date,end_date\n'
                     'WK,0,0,0,0,0,1,0,20260101,20261231\n')  # Saturday only

        self.assertEqual([s.name for s in feed.stations], ['12th Street Station'])

    def test_directional_suffixes_are_stripped_from_stop_names(self):
        """
        6,460 of DART's 6,976 stops end in a "- S - FS" operator code. It says
        which pole to service and title-cases into the broken-looking "- S - Fs".
        """
        stops = ('stop_id,stop_name,stop_lat,stop_lon\n'
                 'S2,LUNA @ VALLEY VIEW - S - FS,32.81,-96.81\n')
        feed = gtfs.parse_feed(_gtfs_zip(
            routes=self.ROUTES, stops=stops,
            trips='route_id,service_id,trip_id\nB1,WK,t_busy\n',
            stop_times=_stop_times([('t_busy', 'S2', 80)]),
            calendar=self.CALENDAR))

        self.assertEqual([s.name for s in feed.stations], ['Luna @ Valley View'])

    def test_station_carries_mode_and_routes(self):
        feed = self._parse()
        station = next(s for s in feed.stations if s.name == '12th Street Station')

        self.assertEqual(station.mode, 'light_rail')
        self.assertTrue(station.is_rail)
        self.assertEqual(station.route_ids, ['R1'])

        bus = next(s for s in feed.stations if s.name == 'Main @ 1st')
        self.assertFalse(bus.is_rail)

    def test_route_colours_and_frequency(self):
        feed = self._parse()
        red = next(r for r in feed.routes if r.source_id == 'R1')

        self.assertEqual(red.color, 'FD3E3E')
        self.assertEqual(red.mode, 'light_rail')

        busy = next(r for r in feed.routes if r.source_id == 'B1')
        self.assertEqual(busy.trips_per_weekday, 80)
        self.assertTrue(busy.is_frequent)

        thin = next(r for r in feed.routes if r.source_id == 'B2')
        self.assertEqual(thin.trips_per_weekday, 10)
        self.assertFalse(thin.is_frequent)
        # F1 is a ferry: no stop of its own survives, so the route goes too.
        self.assertNotIn('F1', {r.source_id for r in feed.routes})

    def test_calendar_dates_only_feed_is_counted(self):
        """
        CapMetro ships no calendar.txt at all — service is entirely exceptions.

        Reading only calendar.txt scored every one of its stops at zero trips,
        which silently dropped every frequent bus stop in Austin.
        """
        # 20260826 is a Wednesday.
        feed = self._parse(calendar=None,
                           calendar_dates='service_id,date,exception_type\n'
                                          'WK,20260826,1\n')
        by_name = {s.name: s for s in feed.stations}

        self.assertEqual(by_name['Main @ 1st'].trips_per_weekday, 80)
        self.assertEqual(by_name['Quiet @ 2nd'].trips_per_weekday, 10)

    def test_holiday_weekend_service_does_not_inflate_a_weekday(self):
        """
        DART adds its *Sunday* services on Labor Day, a Monday.

        Folded in naively, Monday gets a weekday timetable plus a full Sunday
        one; because the count takes the busiest weekday, that fabricated day
        wins and more than doubles the stops clearing the threshold.
        """
        calendar = self.CALENDAR + 'SU,0,0,0,0,0,0,1,20260101,20261231\n'
        trips = self.TRIPS + 'B2,SU,t_quiet_sun\n'
        # On its own the Sunday trip is well under the threshold; added to
        # Monday's weekday total it would carry S3 over it.
        times = self.TIMES + _stop_times([('t_quiet_sun', 'S3', 55)])
        feed = gtfs.parse_feed(_gtfs_zip(
            routes=self.ROUTES, stops=self.STOPS, trips=trips,
            stop_times=times, calendar=calendar,
            # 20260907 is Labor Day, a Monday.
            calendar_dates='service_id,date,exception_type\nSU,20260907,1\n'))

        by_name = {s.name: s for s in feed.stations}
        # Weekday service only — not weekday plus a Sunday timetable on top.
        self.assertEqual(by_name['Quiet @ 2nd'].trips_per_weekday, 10)
        self.assertLess(by_name['Quiet @ 2nd'].trips_per_weekday,
                        gtfs.FREQUENT_TRIPS_PER_WEEKDAY)

    def test_parent_station_platforms_collapse(self):
        """A four-platform station is one row, not four."""
        stops = ('stop_id,stop_name,stop_lat,stop_lon,location_type,parent_station\n'
                 'P0,UNION STATION,32.80,-96.80,1,\n'
                 'P1,UNION STATION PLATFORM 1,32.80,-96.80,0,P0\n'
                 'P2,UNION STATION PLATFORM 2,32.80,-96.80,0,P0\n')
        times = _stop_times([('t_rail', 'P0', 6), ('t_rail', 'P1', 6),
                             ('t_rail', 'P2', 6)])
        feed = gtfs.parse_feed(_gtfs_zip(
            routes=self.ROUTES, stops=stops,
            trips='route_id,service_id,trip_id\nR1,WK,t_rail\n',
            stop_times=times, calendar=self.CALENDAR))

        self.assertEqual([s.name for s in feed.stations], ['Union Station'])

    def test_shouted_names_are_title_cased(self):
        self.assertEqual(gtfs._title('12TH STREET STATION'), '12th Street Station')
        self.assertEqual(gtfs._title('MCKINNEY AVENUE TROLLEY'), 'McKinney Avenue Trolley')
        self.assertEqual(gtfs._title('SMU/MOCKINGBIRD STATION'), 'SMU/Mockingbird Station')
        # Already mixed case — the agency knew what it meant.
        self.assertEqual(gtfs._title('CityLine/Bush'), 'CityLine/Bush')

    def test_unreadable_payload_returns_none(self):
        """None, not an exception and not an empty feed — see load_feed."""
        self.assertIsNone(gtfs.parse_feed(b'not a zip'))


class TransitProximityTests(TestCase):
    """Covers services.transit and the Commute Score built on top of it."""

    def setUp(self):
        patcher = mock.patch('listings.services.geocoding.geocode_address',
                             return_value=None)
        patcher.start()
        self.addCleanup(patcher.stop)

        self.agency = TransitAgency.objects.create(
            slug='test', name='TEST', gtfs_url='https://example.com/gtfs.zip')
        self.red = TransitRoute.objects.create(
            agency=self.agency, source_id='R', short_name='RED',
            mode='light_rail', color='FD3E3E', trips_per_weekday=200,
            is_frequent=True)
        self.tre = TransitRoute.objects.create(
            agency=self.agency, source_id='T', short_name='TRE',
            mode='commuter_rail', color='112458', trips_per_weekday=40)

        self.owner = User.objects.create_user(username='transitowner', password='pw')
        self.listing = Listing.objects.create(
            owner=self.owner, title='Transit Rental', category='rentals',
            price=Decimal('1500'), city='Dallas', state='TX', status='active',
            latitude=Decimal('32.800000'), longitude=Decimal('-96.800000'))

    def _station(self, name, lat, lng, *, mode='light_rail', routes=(), rail=True):
        station = TransitStation.objects.create(
            agency=self.agency, source_id=name, name=name,
            latitude=Decimal(str(lat)), longitude=Decimal(str(lng)),
            mode=mode, is_rail=rail, trips_per_weekday=120)
        for route in routes:
            StationRoute.objects.create(station=station, route=route)
        return station

    def test_nearest_rail_wins_over_a_higher_ranked_mode_further_away(self):
        """
        Distance decides between two rail stations; mode must not.

        Ranking by mode first put a commuter-rail station 3.9 miles away ahead
        of the light-rail station across the street, because commuter rail
        outranks light rail. A listing on top of SMU/Mockingbird scored 47.
        """
        near = self._station('Near Light Rail', 32.8005, -96.8005,
                             mode='light_rail', routes=[self.red])
        self._station('Far Commuter Rail', 32.8600, -96.8600,
                      mode='commuter_rail', routes=[self.tre])

        matches = transit.nearest_stations(Decimal('32.800000'), Decimal('-96.800000'))

        self.assertEqual(matches[0][0], near)
        self.assertLess(matches[0][1], 0.1)

    def test_rail_and_surface_have_independent_limits(self):
        """
        The card shows rail and bus in separate sections, so they do not compete
        for slots. An earlier version spent one budget of three with a single
        slot held for surface, which capped a listing at one bus stop however
        many distinct routes it had.
        """
        for i in range(5):
            self._station(f'Rail {i}', 32.80 + i / 1000, -96.80, routes=[self.red])
        buses = []
        for i in range(4):
            route = TransitRoute.objects.create(
                agency=self.agency, source_id=f'B{i}', short_name=str(60 + i),
                mode='bus', trips_per_weekday=90, is_frequent=True)
            buses.append(self._station(f'Bus {i}', 32.8008 + i / 1000, -96.8000,
                                       mode='bus', rail=False, routes=[route]))

        matches = transit.nearest_stations(Decimal('32.800000'), Decimal('-96.800000'))
        rail = [st for st, _ in matches if st.is_rail]
        surface = [st for st, _ in matches if not st.is_rail]

        self.assertEqual(len(rail), transit.DEFAULT_RAIL_LIMIT)
        self.assertEqual(len(surface), transit.DEFAULT_SURFACE_LIMIT)
        # Rail still leads the list.
        self.assertTrue(matches[0][0].is_rail)

    def test_a_stop_adding_no_new_route_is_dropped(self):
        """
        Bus stops are directional and come in pairs, and feeds name the two
        poles from opposite streets, so they do not look like duplicates.
        Valley Ranch showed "Luna @ Valley View" and "Valley View @ Luna" —
        both route 227 — as two of its three bus rows.
        """
        route = TransitRoute.objects.create(
            agency=self.agency, source_id='B7', short_name='227',
            mode='bus', trips_per_weekday=90, is_frequent=True)
        near = self._station('Luna @ Valley View', 32.8008, -96.8000,
                             mode='bus', rail=False, routes=[route])
        self._station('Valley View @ Luna', 32.8009, -96.8000,
                      mode='bus', rail=False, routes=[route])

        surface = [st for st, _ in
                   transit.nearest_stations(Decimal('32.800000'), Decimal('-96.800000'))
                   if not st.is_rail]

        self.assertEqual(surface, [near])

    def test_a_match_older_than_the_last_import_is_stale(self):
        """
        Stations only move when a feed is re-imported, so a match from before
        the newest import is out of date however recent it is.

        Without this the symptom is silent: `fetch_transit` reports "0 candidate
        rows", exits successfully, and the card keeps showing the old set. It
        cost two rounds of "the bus stops still aren't there".
        """
        cache.clear()
        self._station('Rail', 32.8005, -96.8005, routes=[self.red])
        transit.sync_instance(self.listing)
        self.listing.refresh_from_db()
        self.assertFalse(transit.is_stale(self.listing))

        # A later import moves the station table under the existing match.
        TransitAgency.objects.update(last_imported=timezone.now())
        cache.clear()

        self.assertTrue(transit.is_stale(self.listing))

    def test_an_agency_never_imported_does_not_make_everything_stale(self):
        """A null last_imported must not read as 'imported at the epoch'."""
        cache.clear()
        self._station('Rail', 32.8005, -96.8005, routes=[self.red])
        transit.sync_instance(self.listing)
        self.listing.refresh_from_db()

        TransitAgency.objects.update(last_imported=None)
        cache.clear()

        self.assertIsNone(transit.latest_import_at())
        self.assertFalse(transit.is_stale(self.listing))

    def test_score_is_none_until_the_listing_has_been_matched(self):
        """
        Unmatched is 'we do not know', not zero.

        A hard zero on the card would read as a claim we cannot support.
        """
        self.assertIsNone(commute_score.score_listing(self.listing))

        self.listing.latitude = None
        self.assertIsNone(commute_score.score_listing(self.listing))

    def test_score_rewards_rail_proximity_and_line_count(self):
        self._station('Interchange', 32.8005, -96.8005, routes=[self.red, self.tre])
        transit.sync_instance(self.listing)
        self.listing.refresh_from_db()
        self.listing.downtown_drive_minutes = 10

        result = commute_score.score_listing(self.listing)

        # Rail at the door takes the full access allocation, undiscounted.
        self.assertEqual(result.components['transit_access'],
                         commute_score.ACCESS_POINTS)
        self.assertEqual(result.components['network_reach'],
                         commute_score.REACH_POINTS[2])
        self.assertEqual(result.components['downtown_drive'],
                         commute_score.DOWNTOWN_POINTS)
        self.assertEqual(result.score, 94)
        self.assertEqual(result.label, 'Exceptional Transit')

    def test_score_is_zero_but_present_where_nothing_is_in_range(self):
        """A matched listing with no transit scores zero — that is a finding."""
        transit.sync_instance(self.listing)
        self.listing.refresh_from_db()

        result = commute_score.score_listing(self.listing)

        self.assertEqual(result.score, 0)
        self.assertEqual(result.label, 'Car-Dependent')

    def test_two_stations_on_one_line_count_as_one_line(self):
        """Reach counts lines, not stations — a corridor is not an interchange."""
        self._station('Stop A', 32.8005, -96.8005, routes=[self.red])
        self._station('Stop B', 32.8105, -96.8105, routes=[self.red])
        transit.sync_instance(self.listing)
        self.listing.refresh_from_db()

        result = commute_score.score_listing(self.listing)

        self.assertEqual(result.components['network_reach'],
                         commute_score.REACH_POINTS[1])

    def test_a_bus_only_address_is_not_capped_below_the_rail_bands(self):
        """
        An earlier cut scored rail and bus as separate components and counted
        only rail lines toward reach, so 65 of the 100 points were unreachable
        without rail. A bus-only address was capped at 35 however good its
        service — a corner with four frequent routes and a ten-minute drive
        downtown was permanently "Some Transit".
        """
        routes = [TransitRoute.objects.create(
            agency=self.agency, source_id=f'B{i}', short_name=str(50 + i),
            mode='bus', trips_per_weekday=90, is_frequent=True) for i in range(4)]
        self._station('Busy Corner', 32.8010, -96.8000,
                      mode='bus', rail=False, routes=routes)
        transit.sync_instance(self.listing)
        self.listing.refresh_from_db()
        self.listing.downtown_drive_minutes = 10

        result = commute_score.score_listing(self.listing)

        # A bus stop earns its mode's share of the access allocation, not all
        # of it, and four frequent routes count as two line-equivalents.
        self.assertEqual(result.components['transit_access'],
                         round(commute_score.ACCESS_POINTS
                               * commute_score.MODE_ACCESS_FACTOR['bus'], 1))
        self.assertEqual(result.components['network_reach'],
                         commute_score.REACH_POINTS[2])
        self.assertEqual(result.label, 'Excellent Transit')
        # Still short of what the same address would score with rail.
        self.assertLess(result.score, 100)

    def test_no_transit_at_all_cannot_claim_a_transit_band(self):
        """
        The downtown drive is the one component a listing earns with no transit
        whatsoever, because it measures a car commute. Its ceiling is therefore
        the ceiling for an address with nothing in range, and it must stay below
        the "Some Transit" floor or that address claims a stop it does not have.
        """
        some_transit_floor = dict((label, floor) for floor, label
                                  in commute_score.SCORE_BANDS)['Some Transit']
        self.assertLess(commute_score.DOWNTOWN_POINTS, some_transit_floor)

        transit.sync_instance(self.listing)
        self.listing.refresh_from_db()
        self.listing.downtown_drive_minutes = 1  # right next to downtown

        result = commute_score.score_listing(self.listing)

        self.assertEqual(result.components['transit_access'], 0.0)
        self.assertEqual(result.label, 'Car-Dependent')

    def test_assign_instance_clears_a_score_it_can_no_longer_support(self):
        self.listing.commute_score = 88
        self.listing.commute_score_label = 'Excellent Transit'
        self.listing.latitude = None

        self.assertIsNone(commute_score.assign_instance(self.listing))
        self.assertIsNone(self.listing.commute_score)
        self.assertEqual(self.listing.commute_score_label, '')

    def test_badge_text_colour_is_derived_not_taken_from_the_feed(self):
        """
        DART publishes the Silver Line as C0C0C0 with FFFFFF text — white on
        light grey. The feed does not get to ship us an illegible badge.
        """
        silver = TransitRoute.objects.create(
            agency=self.agency, source_id='S', short_name='SILVER',
            mode='commuter_rail', color='C0C0C0', text_color='FFFFFF')

        self.assertEqual(silver.badge_color, '#C0C0C0')
        self.assertEqual(silver.badge_text_color, '#111827')
        self.assertEqual(self.tre.badge_text_color, '#ffffff')

    def test_route_with_no_colour_falls_back_to_its_mode(self):
        plain = TransitRoute.objects.create(
            agency=self.agency, source_id='P', short_name='55', mode='bus')

        self.assertEqual(plain.badge_color, MODE_BADGE_COLORS['bus'])

    def test_walk_minutes_only_for_walkable_distances(self):
        station = self._station('Walkable', 32.8005, -96.8005, routes=[self.red])
        link = ListingTransitStation.objects.create(
            listing=self.listing, station=station, distance_miles=Decimal('0.4'))
        self.assertEqual(link.walk_minutes, 8)

        link.distance_miles = Decimal('2.5')
        self.assertIsNone(link.walk_minutes)

    def test_drive_time_matrix_includes_stations(self):
        """
        Stations ride along in the downtown/grocery matrix rather than taking a
        call of their own — Routes bills per element, so extra destinations on
        an existing request are far cheaper than a second request.
        """
        station = self._station('Rail', 32.8005, -96.8005, routes=[self.red])
        transit.sync_instance(self.listing)
        self.listing.refresh_from_db()

        with mock.patch('listings.services.drivetime.fetch_drive_matrix',
                        return_value={0: {'minutes': 7, 'miles': 2.1}}) as matrix:
            drivetime.sync_instance(self.listing, force=True)

        _, targets = matrix.call_args[0]
        self.assertEqual(len(targets), 1)  # one station, no downtown or grocery
        link = self.listing.nearby_transit.get(station=station)
        self.assertEqual(link.drive_minutes, 7)

    def test_detail_page_shows_the_commute_card_and_not_transit_score(self):
        self._station('Deep Ellum Station', 32.8005, -96.8005,
                      routes=[self.red, self.tre])
        bus_route = TransitRoute.objects.create(
            agency=self.agency, source_id='B5', short_name='227', mode='bus')
        self._station('Luna @ Valley View', 32.8008, -96.8000,
                      mode='bus', rail=False, routes=[bus_route])
        transit.sync_instance(self.listing)
        self.listing.refresh_from_db()
        commute_score.assign_instance(self.listing)
        self.listing.save()
        # Populated but deliberately not rendered — see Listing.walk_score_rows.
        Listing.objects.filter(pk=self.listing.pk).update(
            walk_score=91, walk_score_description="Walker's Paradise",
            # A description no band name could collide with — 'Good Transit'
            # is itself a Commute Score band, so it proves nothing here.
            transit_score=62, transit_description='WALKSCORE-TRANSIT-MARKER')

        html = self.client.get(reverse('listing_detail',
                                       args=[self.listing.pk])).content.decode()

        self.assertIn('Commute Score', html)
        self.assertIn(self.listing.commute_score_label, html)
        # Rail and bus are shown as separate sections.
        self.assertIn('Rail stations', html)
        self.assertIn('Bus stops', html)
        self.assertIn('Deep Ellum Station', html)
        self.assertIn('#FD3E3E', html)          # the Red Line badge
        self.assertIn('Luna @ Valley View', html)
        self.assertLess(html.index('Rail stations'), html.index('Bus stops'))
        # The Walk Score card is untouched; only its transit row is gone.
        self.assertIn('Walk Score', html)
        self.assertIn('Walker&#x27;s Paradise', html)  # escaped by the template
        self.assertNotIn('Transit Score', html)
        self.assertNotIn('WALKSCORE-TRANSIT-MARKER', html)


class SearchIncludesCommunitiesTests(TestCase):
    """
    The default /listings/ view must show community inventory.

    `category` is blank unless a tab is chosen, and blank was being compared
    against 'rentals' as a mismatch — so the page a renter lands on after
    signing in showed standalone listings only, and communities appeared only
    once a category landed in the URL.
    """

    def setUp(self):
        self.community = Community.objects.create(
            name='Maple Court', description='', city='Dallas',
            community_type='apartment_complex', status='active')

    def test_a_bare_search_includes_communities(self):
        response = self.client.get('/listings/')

        self.assertEqual(list(response.context['communities']), [self.community])

    def test_the_rent_tab_includes_communities(self):
        response = self.client.get('/listings/?category=rentals')

        self.assertEqual(list(response.context['communities']), [self.community])

    def test_the_buy_tab_excludes_communities(self):
        response = self.client.get('/listings/?category=properties')

        self.assertEqual(list(response.context['communities']), [])

    def test_a_signed_in_renter_still_sees_them(self):
        renter = User.objects.create_user('renter', 'r@example.com', 'pw')
        self.client.force_login(renter)

        response = self.client.get('/listings/')

        self.assertEqual(list(response.context['communities']), [self.community])


class SignInReturnsYouWhereYouWereTests(TestCase):
    """Signing in from the home page landed you on /listings/ instead."""

    def test_the_nav_sign_in_link_carries_the_current_page(self):
        response = self.client.get('/')

        self.assertContains(response, '/accounts/login/?next=/')

    def test_signing_in_from_home_returns_to_home(self):
        user = User.objects.create_user('renter', 'r@example.com', 'pw')

        response = self.client.post('/accounts/login/', {
            'username': 'renter', 'password': 'pw', 'next': '/',
        })

        # Login is two-legged; the destination has to outlive the OTP screen.
        self.assertRedirects(response, '/accounts/login/confirm/',
                             fetch_redirect_response=False)
        self.assertEqual(self.client.session['pw_otp_next'], '/')


class CommunityMapMarkerTests(TestCase):
    """
    Community cards must carry the attributes the map reads.

    `_placeMarkers` selects `.listing-card[data-city]`, so a community card
    without those data-* attributes was silently skipped — the property showed
    in the list and vanished on the map.
    """

    def setUp(self):
        self.community = Community.objects.create(
            name='Maple Court', description='', city='Dallas',
            address_line='4521 Maple Ave', community_type='apartment_complex',
            status='active', latitude='32.811871', longitude='-96.823574')
        floor_plan = FloorPlan.objects.create(
            community=self.community, name='A1', bedrooms=1, bathrooms=1)
        Unit.objects.create(floor_plan=floor_plan, unit_number='101',
                            price=1450, status='available')

    def test_the_card_carries_the_coordinates_the_map_needs(self):
        response = self.client.get('/listings/')
        html = response.content.decode()

        self.assertIn('data-city="Dallas"', html)
        self.assertIn('data-lat="32.811871"', html)
        self.assertIn('data-lng="-96.823574"', html)
        self.assertIn('data-title="Maple Court"', html)
        self.assertIn('data-price="1450', html)

    def test_the_card_is_still_tagged_as_a_community(self):
        """The pin builds its link from data-kind; listing pks are a different space."""
        response = self.client.get('/listings/')

        self.assertContains(response, 'data-kind="community"')
