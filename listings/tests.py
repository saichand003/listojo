import io
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.core import mail
from django.test import Client, TestCase

from listings.models import Community, FloorPlan, GuidedSearchEvent, Listing, ListingInquiry, Unit, UserListingEvent
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
