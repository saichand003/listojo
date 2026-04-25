from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from chatapp.models import ChatMessage
from listings.models import Listing
from listings.services.visibility import active_listings
from portal.models import Lead, Shortlist
from portal.services.lead_service import create_or_update_lead
from portal.services.routing import auto_assign
from portal.services.shortlist_service import create_and_send


class ModularMonolithServiceTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='owner', password='pw')
        self.agent_a = User.objects.create_user(username='agent-a', password='pw', is_staff=True)
        self.agent_b = User.objects.create_user(username='agent-b', password='pw', is_staff=True)

        self.visible_listing = Listing.objects.create(
            owner=self.owner,
            title='Visible Listing',
            description='A current active listing',
            category='rentals',
            city='Irving',
            price=1800,
            bedrooms=2,
            tags='pet-friendly, parking',
            status='active',
        )
        self.expired_listing = Listing.objects.create(
            owner=self.owner,
            title='Expired Listing',
            description='Should not surface',
            category='rentals',
            city='Irving',
            price=1700,
            status='active',
            expires_at=date.today() - timedelta(days=1),
        )
        self.pending_listing = Listing.objects.create(
            owner=self.owner,
            title='Pending Listing',
            description='Should not surface',
            category='rentals',
            city='Irving',
            price=1600,
            status='pending',
        )

    def test_active_listings_applies_shared_visibility_rules(self):
        visible_ids = set(active_listings().values_list('id', flat=True))
        self.assertIn(self.visible_listing.id, visible_ids)
        self.assertNotIn(self.expired_listing.id, visible_ids)
        self.assertNotIn(self.pending_listing.id, visible_ids)

    def test_guided_search_leads_dedup_and_update_preference(self):
        lead = create_or_update_lead(
            name='Priya',
            email='priya@example.com',
            source='guided_search',
            city='Irving',
            property_type='rentals',
            bedrooms=2,
            max_budget=Decimal('2200'),
            amenities='pet-friendly, parking',
        )
        updated = create_or_update_lead(
            name='Priya',
            email='priya@example.com',
            source='guided_search',
            city='Plano',
            property_type='rentals',
            bedrooms=3,
            max_budget=Decimal('2600'),
            amenities='parking',
        )

        self.assertEqual(Lead.objects.filter(email='priya@example.com', source='guided_search').count(), 1)
        self.assertEqual(lead.id, updated.id)
        self.assertEqual(updated.preference.city, 'Plano')
        self.assertEqual(updated.preference.bedrooms, 3)

    def test_inquiry_leads_do_not_dedup(self):
        first = create_or_update_lead(
            name='Arjun',
            email='arjun@example.com',
            source='inquiry',
            listing=self.visible_listing,
        )
        second = create_or_update_lead(
            name='Arjun',
            email='arjun@example.com',
            source='inquiry',
            listing=self.visible_listing,
        )

        self.assertNotEqual(first.id, second.id)
        self.assertEqual(Lead.objects.filter(email='arjun@example.com', source='inquiry').count(), 2)

    def test_auto_assign_and_shortlist_send_follow_shared_services(self):
        lead = create_or_update_lead(
            name='Sonal',
            email='sonal@example.com',
            source='inquiry',
            listing=self.visible_listing,
        )

        assigned = auto_assign(lead)
        self.assertEqual(assigned, self.agent_a)
        self.assertEqual(lead.assigned_agent, self.agent_a)

        shortlist = create_and_send(lead, self.agent_a, [self.visible_listing.id, self.expired_listing.id])
        self.assertIsInstance(shortlist, Shortlist)
        self.assertEqual(shortlist.status, 'sent')
        self.assertEqual(shortlist.items.count(), 1)
        self.assertEqual(shortlist.items.first().listing_id, self.visible_listing.id)

        lead.refresh_from_db()
        self.assertEqual(lead.status, 'shortlist_sent')


class PortalWorkflowTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='owner', password='pw')
        self.agent = User.objects.create_user(username='agent', password='pw', is_staff=True)
        self.superuser = User.objects.create_superuser(username='admin', password='pw', email='admin@example.com')
        self.lead_user = User.objects.create_user(username='rahul', password='pw', email='rahul@example.com')
        self.listing = Listing.objects.create(
            owner=self.owner,
            title='Portal Listing',
            description='Review me',
            category='rentals',
            city='Irving',
            price=Decimal('1900.00'),
            status='pending',
        )
        self.lead = create_or_update_lead(
            name='Rahul',
            email='rahul@example.com',
            source='inquiry',
            listing=self.listing,
            city='Irving',
            property_type='rentals',
            bedrooms=2,
            max_budget=Decimal('2200.00'),
        )

    def test_request_agent_assigns_session_lead(self):
        session = self.client.session
        session['gs_lead_id'] = self.lead.pk
        session.save()

        response = self.client.post('/portal/agent/request/')
        self.assertEqual(response.status_code, 200)
        self.lead.refresh_from_db()
        self.assertEqual(self.lead.assigned_agent, self.agent)
        self.assertNotIn('gs_lead_id', self.client.session)

    def test_agent_lead_detail_requires_assignment_or_superuser(self):
        outsider = User.objects.create_user(username='outsider', password='pw', is_staff=True)

        self.client.force_login(outsider)
        response = self.client.get(f'/portal/agent/leads/{self.lead.pk}/')
        self.assertEqual(response.status_code, 404)

        self.lead.assigned_agent = self.agent
        self.lead.save()
        self.client.force_login(self.agent)
        response = self.client.get(f'/portal/agent/leads/{self.lead.pk}/')
        self.assertEqual(response.status_code, 200)

        self.client.force_login(self.superuser)
        response = self.client.get(f'/portal/agent/leads/{self.lead.pk}/')
        self.assertEqual(response.status_code, 200)

    def test_agent_dashboard_shows_unread_message_badge(self):
        self.lead.assigned_agent = self.agent
        self.lead.save()
        ChatMessage.objects.create(
            listing=self.listing,
            sender=self.owner,
            recipient=self.agent,
            message='New client update',
        )

        self.client.force_login(self.agent)
        response = self.client.get(reverse('agent_dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse('agent_messages'))
        self.assertContains(response, '💬</span> Messages')
        self.assertContains(response, '<span class="sidebar-badge">1</span>', html=True)

    def test_agent_messages_uses_agent_portal_page(self):
        self.lead.assigned_agent = self.agent
        self.lead.save()
        ChatMessage.objects.create(
            listing=self.listing,
            sender=self.owner,
            recipient=self.agent,
            message='Agent-specific inbox message',
        )

        self.client.force_login(self.agent)
        response = self.client.get(reverse('agent_messages'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Agent Portal')
        self.assertContains(response, 'Agent-specific inbox message')

    def test_agent_clients_groups_working_records_by_person(self):
        self.lead.assigned_agent = self.agent
        self.lead.status = 'shortlist_sent'
        self.lead.notes = 'Next step: confirm weekend tour availability'
        self.lead.save()

        create_or_update_lead(
            name='Rahul',
            email='rahul@example.com',
            source='guided_search',
            assigned_agent=self.agent,
            city='Plano',
        )

        self.client.force_login(self.agent)
        response = self.client.get(reverse('agent_clients'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Rahul')
        self.assertContains(response, 'My Clients')
        self.assertContains(response, 'Lead Records')
        self.assertContains(response, 'Next step: confirm weekend tour availability')
        self.assertContains(response, reverse('agent_client_detail', args=['rahul@example.com']))

    def test_agent_client_detail_shows_timeline_shortlists_and_messages(self):
        self.lead.assigned_agent = self.agent
        self.lead.status = 'shortlist_sent'
        self.lead.save()
        shortlist = Shortlist.objects.create(lead=self.lead, agent=self.agent, status='sent')
        shortlist.items.create(listing=self.listing, order_index=0)
        ChatMessage.objects.create(
            listing=self.listing,
            sender=self.agent,
            recipient=self.lead_user,
            message='Following up on your shortlist',
        )

        self.client.force_login(self.agent)
        response = self.client.get(reverse('agent_client_detail', args=['rahul@example.com']))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Latest Note')
        self.assertContains(response, 'Notes History')
        self.assertContains(response, 'Timeline')
        self.assertContains(response, 'Shortlist History')
        self.assertContains(response, 'Messages')
        self.assertContains(response, 'Following up on your shortlist')

    def test_superuser_can_approve_flag_and_toggle_featured_listing(self):
        self.client.force_login(self.superuser)

        response = self.client.post(f'/portal/listings/{self.listing.pk}/approve/')
        self.assertEqual(response.status_code, 302)
        self.listing.refresh_from_db()
        self.assertEqual(self.listing.status, 'active')

        self.client.post(f'/portal/listings/{self.listing.pk}/flag/')
        self.listing.refresh_from_db()
        self.assertEqual(self.listing.status, 'flagged')

        self.client.post(f'/portal/listings/{self.listing.pk}/toggle-featured/')
        self.listing.refresh_from_db()
        self.assertTrue(self.listing.featured)

    def test_agent_can_send_curated_shortlist_from_lead_detail(self):
        self.lead.assigned_agent = self.agent
        self.lead.save()
        active_listing = Listing.objects.create(
            owner=self.owner,
            title='Active Match',
            description='Should be shortlisted',
            category='rentals',
            city='Irving',
            price=Decimal('1800.00'),
            bedrooms=2,
            tags='parking',
            status='active',
        )

        self.client.force_login(self.agent)
        response = self.client.post(f'/portal/agent/leads/{self.lead.pk}/', {
            'action': 'send_curated_shortlist',
            'curated_ids': [str(active_listing.pk)],
        })
        self.assertEqual(response.status_code, 302)
        shortlist = Shortlist.objects.get(lead=self.lead)
        self.assertEqual(shortlist.status, 'sent')
        self.assertEqual(shortlist.items.count(), 1)
        self.assertTrue(ChatMessage.objects.filter(
            sender=self.agent,
            recipient=self.lead_user,
            listing=active_listing,
            message__icontains='curated Listojo shortlist',
        ).exists())
        self.client.force_login(self.lead_user)
        thread_response = self.client.get(f'/chat/listing/{active_listing.pk}/with/{self.agent.pk}/thread/')
        self.assertEqual(thread_response.status_code, 200)
        self.assertEqual(len(thread_response.json()['messages']), 1)
        self.lead.refresh_from_db()
        self.assertEqual(self.lead.status, 'shortlist_sent')

        extra_listing = Listing.objects.create(
            owner=self.owner,
            title='Second Match',
            description='Should be appended to the same shortlist',
            category='rentals',
            city='Irving',
            price=Decimal('1750.00'),
            bedrooms=2,
            status='active',
        )
        self.client.force_login(self.agent)
        response = self.client.post(f'/portal/agent/leads/{self.lead.pk}/', {
            'action': 'create_shortlist',
            'listing_ids': [str(extra_listing.pk)],
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Shortlist.objects.filter(lead=self.lead).count(), 1)
        shortlist.refresh_from_db()
        self.assertEqual(shortlist.status, 'draft')
        self.assertEqual(shortlist.items.count(), 2)
