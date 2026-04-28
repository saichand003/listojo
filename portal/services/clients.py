from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from django.contrib.auth.models import User

from chatapp.models import ChatMessage
from portal.models import Lead, Shortlist


CLIENT_STATUSES = [
    'contacted',
    'shortlist_ready',
    'shortlist_sent',
    'touring',
    'application_in_progress',
    'closed_won',
    'closed_lost',
]


def _client_key(lead: Lead) -> str:
    return (lead.email or '').strip().lower()


def _client_display_name(leads: list[Lead]) -> str:
    for lead in leads:
        if lead.name:
            return lead.name
    return 'Unknown client'


def _latest_preference(leads: list[Lead]):
    for lead in sorted(leads, key=lambda item: item.updated_at, reverse=True):
        if hasattr(lead, 'preference'):
            return lead.preference
    return None


def _status_rank(status: str) -> int:
    order = {
        'closed_won': 7,
        'application_in_progress': 6,
        'touring': 5,
        'shortlist_sent': 4,
        'shortlist_ready': 3,
        'contacted': 2,
        'new': 1,
        'closed_lost': 0,
    }
    return order.get(status, -1)


def _latest_status(leads: list[Lead]) -> str:
    sorted_leads = sorted(
        leads,
        key=lambda item: (_status_rank(item.status), item.updated_at),
        reverse=True,
    )
    return sorted_leads[0].status if sorted_leads else 'new'


def _related_user(email: str) -> User | None:
    if not email:
        return None
    return User.objects.filter(email__iexact=email).first()


def _latest_activity(leads: list[Lead], shortlists: list[Shortlist], messages: list[ChatMessage]):
    timestamps = [lead.updated_at for lead in leads]
    timestamps.extend(sl.updated_at for sl in shortlists)
    timestamps.extend(msg.sent_at for msg in messages)
    return max(timestamps) if timestamps else None


def _preferred_cities(leads: list[Lead]) -> list[str]:
    cities: list[str] = []
    for lead in sorted(leads, key=lambda item: item.updated_at, reverse=True):
        pref = getattr(lead, 'preference', None)
        if pref and pref.city and pref.city not in cities:
            cities.append(pref.city)
    return cities[:3]


def _closed_outcomes(leads: list[Lead]) -> list[str]:
    outcomes = []
    for lead in leads:
        if lead.status == 'closed_won' and lead.listing:
            outcomes.append(f'Closed on {lead.listing.title}')
        elif lead.status == 'closed_won' and lead.community:
            outcomes.append(f'Closed on {lead.community.name}')
        elif lead.status == 'closed_lost':
            outcomes.append('Closed lost')
    return outcomes[:3]


def _latest_note(leads: list[Lead]) -> tuple[str, object | None]:
    for lead in sorted(leads, key=lambda item: item.updated_at, reverse=True):
        if lead.notes and lead.notes.strip():
            return lead.notes.strip(), lead.updated_at
    return '', None


def build_client_summaries(agent: User) -> list[dict]:
    leads = list(
        Lead.objects.filter(assigned_agent=agent, status__in=CLIENT_STATUSES)
        .select_related('listing', 'community', 'preference', 'assigned_agent')
        .prefetch_related('shortlists__items__listing')
        .order_by('-updated_at', '-created_at')
    )

    grouped: dict[str, list[Lead]] = defaultdict(list)
    for lead in leads:
        key = _client_key(lead)
        if key:
            grouped[key].append(lead)

    clients = []
    for email, client_leads in grouped.items():
        related_user = _related_user(email)
        latest_lead = max(client_leads, key=lambda item: item.updated_at)
        preference = _latest_preference(client_leads)
        shortlists = []
        for lead in client_leads:
            shortlists.extend(list(lead.shortlists.all()))

        messages = []
        if related_user:
            messages = list(
                ChatMessage.objects.filter(
                    sender=agent,
                    recipient=related_user,
                ) | ChatMessage.objects.filter(
                    sender=related_user,
                    recipient=agent,
                )
            )

        latest_note, latest_note_updated_at = _latest_note(client_leads)

        clients.append({
            'slug': email,
            'name': _client_display_name(client_leads),
            'email': email,
            'phone': next((lead.phone for lead in client_leads if lead.phone), ''),
            'assigned_agent': agent,
            'latest_status': _latest_status(client_leads),
            'preferred_cities': _preferred_cities(client_leads),
            'budget': preference.max_budget if preference else None,
            'bedrooms': preference.bedrooms if preference else None,
            'last_activity': _latest_activity(client_leads, shortlists, messages),
            'guided_search_count': sum(1 for lead in client_leads if lead.source == 'guided_search'),
            'lead_count': len(client_leads),
            'shortlists_sent_count': sum(1 for sl in shortlists if sl.status in ('sent', 'viewed')),
            'messages_count': len(messages),
            'outcomes': _closed_outcomes(client_leads),
            'latest_note': latest_note,
            'latest_note_updated_at': latest_note_updated_at,
            'latest_lead': latest_lead,
        })

    return sorted(
        clients,
        key=lambda item: (item['last_activity'] is not None, item['last_activity']),
        reverse=True,
    )


def build_client_profile(agent: User, email: str) -> dict | None:
    leads = list(
        Lead.objects.filter(assigned_agent=agent, email__iexact=email)
        .select_related('listing', 'community', 'preference', 'assigned_agent')
        .prefetch_related('shortlists__items__listing')
        .order_by('-updated_at', '-created_at')
    )
    if not leads:
        return None

    related_user = _related_user(email)
    shortlists = []
    for lead in leads:
        shortlists.extend(list(lead.shortlists.all()))
    shortlists = sorted(shortlists, key=lambda item: item.created_at, reverse=True)

    messages = []
    if related_user:
        messages = list(
            (
                ChatMessage.objects.filter(sender=agent, recipient=related_user)
                | ChatMessage.objects.filter(sender=related_user, recipient=agent)
            )
            .select_related('listing', 'sender', 'recipient')
            .order_by('-sent_at')
        )

    latest_pref = _latest_preference(leads)
    latest_status = _latest_status(leads)
    latest_note, latest_note_updated_at = _latest_note(leads)
    notes_history = [lead for lead in leads if lead.notes and lead.notes.strip()]

    timeline = []
    for lead in leads:
        timeline.append({
            'when': lead.created_at,
            'type': 'lead',
            'title': f"{lead.get_source_display()} lead created",
                'detail': lead.listing.title if lead.listing else (lead.community.name if lead.community else lead.get_status_display()),
        })
        if lead.updated_at != lead.created_at:
            timeline.append({
                'when': lead.updated_at,
                'type': 'status',
                'title': 'Lead updated',
                'detail': lead.get_status_display(),
            })
    for shortlist in shortlists:
        timeline.append({
            'when': shortlist.sent_at or shortlist.updated_at,
            'type': 'shortlist',
            'title': f"Shortlist {shortlist.get_status_display().lower()}",
            'detail': f"{shortlist.items.count()} listing{'s' if shortlist.items.count() != 1 else ''}",
        })
    for message in messages:
        timeline.append({
            'when': message.sent_at,
            'type': 'message',
            'title': f"Message from {message.sender.get_full_name() or message.sender.username}",
            'detail': message.message[:120],
        })
    timeline.sort(key=lambda item: item['when'], reverse=True)

    summary = {
        'slug': email.lower(),
        'name': _client_display_name(leads),
        'email': email,
        'phone': next((lead.phone for lead in leads if lead.phone), ''),
        'assigned_agent': agent,
        'latest_status': latest_status,
        'preferred_cities': _preferred_cities(leads),
        'budget': latest_pref.max_budget if latest_pref else None,
        'bedrooms': latest_pref.bedrooms if latest_pref else None,
        'property_type': latest_pref.property_type if latest_pref else '',
        'move_in_date': latest_pref.move_in_date if latest_pref else None,
        'amenities': latest_pref.amenities if latest_pref else '',
        'last_activity': _latest_activity(leads, shortlists, messages),
        'guided_search_count': sum(1 for lead in leads if lead.source == 'guided_search'),
        'lead_count': len(leads),
        'shortlists_sent_count': sum(1 for sl in shortlists if sl.status in ('sent', 'viewed')),
        'outcomes': _closed_outcomes(leads),
        'latest_note': latest_note,
        'latest_note_updated_at': latest_note_updated_at,
    }

    return {
        'client': summary,
        'leads': leads,
        'shortlists': shortlists,
        'messages': messages,
        'timeline': timeline,
        'notes_history': notes_history,
    }
