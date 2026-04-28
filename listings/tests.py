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
