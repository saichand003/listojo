from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase

from listings.models import Listing, ListingInquiry


class AccountDashboardTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='owner', password='pw', is_staff=True)
        self.listing = Listing.objects.create(
            owner=self.user,
            title='Owner Listing',
            description='Owner dashboard listing',
            category='rentals',
            city='Plano',
            price=Decimal('2100.00'),
            status='active',
            view_count=9,
        )
        ListingInquiry.objects.create(
            listing=self.listing,
            name='Lead User',
            email='lead@example.com',
            message='Interested',
        )

    def test_owner_dashboards_render(self):
        self.client.force_login(self.user)

        self.assertEqual(self.client.get('/accounts/my-listings/').status_code, 200)
        self.assertEqual(self.client.get('/accounts/performance/').status_code, 200)
        self.assertEqual(self.client.get('/accounts/inquiries/').status_code, 200)
        self.assertEqual(self.client.get('/accounts/agent/').status_code, 200)
