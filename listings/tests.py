from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.core import mail
from django.test import TestCase

from listings.models import GuidedSearchEvent, Listing, ListingInquiry
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

    def test_listing_list_hides_expired_listing(self):
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        listings = response.context['listings']
        self.assertIn(self.active_listing, listings)
        self.assertNotIn(self.expired_listing, listings)

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
