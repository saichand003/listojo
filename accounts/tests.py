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

    def test_inquiries_overview_marks_unread_inquiries_as_read(self):
        self.client.force_login(self.user)

        response = self.client.get('/accounts/inquiries/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(ListingInquiry.objects.filter(listing=self.listing, is_read=False).count(), 0)

    def test_unread_inquiry_count_endpoint_returns_only_unread_items(self):
        ListingInquiry.objects.create(
            listing=self.listing,
            name='Read Lead',
            email='read@example.com',
            message='Already reviewed',
            is_read=True,
        )
        self.client.force_login(self.user)

        response = self.client.get('/accounts/inquiries/unread-count/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['unread_count'], 1)

    def test_inquiries_overview_uses_view_inquiry_link(self):
        inquiry = ListingInquiry.objects.get(listing=self.listing)
        self.client.force_login(self.user)

        response = self.client.get('/accounts/inquiries/')

        self.assertContains(response, 'View inquiry')
        self.assertContains(response, f'/inquiries/{inquiry.pk}/')

    def test_listing_inquiries_page_has_back_to_all_inquiries_link(self):
        self.client.force_login(self.user)

        response = self.client.get(f'/listing/{self.listing.pk}/inquiries/')

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Back to All Inquiries')

    def test_inquiry_detail_page_renders_single_inquiry(self):
        inquiry = ListingInquiry.objects.get(listing=self.listing)
        self.client.force_login(self.user)

        response = self.client.get(f'/inquiries/{inquiry.pk}/')

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, inquiry.name)
        self.assertContains(response, inquiry.message)
        self.assertContains(response, 'Back to All Inquiries')
