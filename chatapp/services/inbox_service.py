from __future__ import annotations

from django.db.models import Q

from chatapp.models import ChatMessage


def build_listing_conversations(user) -> list[dict]:
    seen = set()
    listing_conversations = []

    for msg in ChatMessage.objects.filter(
        listing__isnull=False,
    ).filter(
        Q(sender=user) | Q(recipient=user)
    ).select_related('listing', 'sender', 'recipient').order_by('-sent_at'):
        other = msg.recipient if msg.sender == user else msg.sender
        key = (msg.listing_id, other.pk)
        if key in seen:
            continue
        seen.add(key)

        unread_count = ChatMessage.objects.filter(
            listing=msg.listing,
            recipient=user,
            is_read=False,
            sender=other,
        ).count()
        listing_conversations.append({
            'listing': msg.listing,
            'user': other,
            'last_message': msg,
            'is_owner': msg.listing.owner == user,
            'unread_count': unread_count,
        })

    return listing_conversations
