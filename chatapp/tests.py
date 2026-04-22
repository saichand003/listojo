from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase

from chatapp.models import ChatMessage
from listings.models import Listing
from portal.models import Lead


class ChatLeadCaptureTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='owner', password='pw')
        self.visitor = User.objects.create_user(
            username='visitor',
            password='pw',
            email='visitor@example.com',
            first_name='Visitor',
        )
        self.listing = Listing.objects.create(
            owner=self.owner,
            title='Chat Listing',
            description='Listing with chat',
            category='rentals',
            city='Dallas',
            price=Decimal('1750.00'),
            status='active',
        )

    def test_listing_chat_send_creates_chat_lead_once(self):
        self.client.force_login(self.visitor)

        first = self.client.post(f'/chat/listing/{self.listing.pk}/send/', {'message': 'Hello'})
        second = self.client.post(f'/chat/listing/{self.listing.pk}/send/', {'message': 'Following up'})

        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 201)
        self.assertEqual(ChatMessage.objects.filter(listing=self.listing).count(), 2)
        self.assertEqual(Lead.objects.filter(email='visitor@example.com', listing=self.listing, source='chat').count(), 1)

    def test_owner_cannot_use_visitor_listing_chat_send_path(self):
        self.client.force_login(self.owner)
        response = self.client.post(f'/chat/listing/{self.listing.pk}/send/', {'message': 'Owner message'})
        self.assertEqual(response.status_code, 400)
