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

    def test_consumer_navigation_shows_unread_message_badge(self):
        ChatMessage.objects.create(
            listing=self.listing,
            sender=self.owner,
            recipient=self.visitor,
            message='Unread consumer message',
        )

        self.client.force_login(self.visitor)
        response = self.client.get('/')

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<span class="sb-badge">1</span>', html=True)
        self.assertContains(response, 'Messages (1)')

    def test_unread_count_endpoint_returns_current_count(self):
        ChatMessage.objects.create(
            listing=self.listing,
            sender=self.owner,
            recipient=self.visitor,
            message='Unread one',
        )
        ChatMessage.objects.create(
            listing=self.listing,
            sender=self.owner,
            recipient=self.visitor,
            message='Unread two',
        )

        self.client.force_login(self.visitor)
        response = self.client.get('/chat/unread-count/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['unread_count'], 2)

    def test_listing_thread_reports_other_party_typing_state(self):
        self.client.force_login(self.visitor)
        typing_response = self.client.post(
            f'/chat/listing/{self.listing.pk}/typing/',
            {'is_typing': 'true'},
        )

        self.assertEqual(typing_response.status_code, 200)

        self.client.force_login(self.owner)
        thread_response = self.client.get(
            f'/chat/listing/{self.listing.pk}/with/{self.visitor.pk}/thread/'
        )

        self.assertEqual(thread_response.status_code, 200)
        self.assertTrue(thread_response.json()['other_user_typing'])

    def test_listing_thread_typing_state_clears_when_stopped(self):
        self.client.force_login(self.visitor)
        self.client.post(f'/chat/listing/{self.listing.pk}/typing/', {'is_typing': 'true'})
        stop_response = self.client.post(
            f'/chat/listing/{self.listing.pk}/typing/',
            {'is_typing': 'false'},
        )

        self.assertEqual(stop_response.status_code, 200)

        self.client.force_login(self.owner)
        thread_response = self.client.get(
            f'/chat/listing/{self.listing.pk}/with/{self.visitor.pk}/thread/'
        )

        self.assertEqual(thread_response.status_code, 200)
        self.assertFalse(thread_response.json()['other_user_typing'])
