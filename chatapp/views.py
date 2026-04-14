import uuid

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_POST

from listings.models import Listing, ListingInquiry

from .forms import GuestMessageForm, MessageForm
from .models import ChatMessage, GuestChatMessage


@login_required
def inbox(request):
    listing_inquiries = ListingInquiry.objects.filter(
        listing__owner=request.user
    ).select_related('listing').order_by('-created_at')

    # All chat messages tied to listings where the user is a participant
    # (either as owner or as the visitor who messaged). Deduplicate into
    # one entry per (listing, other_user) pair.
    seen = set()
    listing_conversations = []
    for msg in ChatMessage.objects.filter(
        listing__isnull=False,
    ).filter(
        Q(sender=request.user) | Q(recipient=request.user)
    ).select_related('listing', 'sender', 'recipient').order_by('-sent_at'):
        other = msg.recipient if msg.sender == request.user else msg.sender
        key = (msg.listing_id, other.pk)
        if key not in seen:
            seen.add(key)
            listing_conversations.append({
                'listing': msg.listing,
                'user': other,
                'last_message': msg,
                'is_owner': msg.listing.owner == request.user,
            })

    guest_messages = GuestChatMessage.objects.filter(
        recipient=request.user
    ).order_by('-sent_at')

    return render(request, 'chatapp/inbox.html', {
        'listing_inquiries': listing_inquiries,
        'listing_conversations': listing_conversations,
        'guest_messages': guest_messages,
    })


@login_required
def conversation(request, user_id):
    other_user = get_object_or_404(User, pk=user_id)
    messages_qs = ChatMessage.objects.filter(
        Q(sender=request.user, recipient=other_user)
        | Q(sender=other_user, recipient=request.user)
    ).select_related('sender', 'recipient')

    if request.method == 'POST':
        form = MessageForm(request.POST)
        if form.is_valid():
            msg = form.save(commit=False)
            msg.sender = request.user
            msg.recipient = other_user
            msg.save()
            return redirect('conversation', user_id=other_user.pk)
    else:
        form = MessageForm()

    return render(
        request,
        'chatapp/conversation.html',
        {'other_user': other_user, 'messages': messages_qs, 'form': form},
    )


def guest_conversation(request, user_id):
    other_user = get_object_or_404(User, pk=user_id)

    if request.method == 'POST':
        form = GuestMessageForm(request.POST)
        if form.is_valid():
            guest_msg = form.save(commit=False)
            guest_msg.recipient = other_user
            guest_msg.guest_session_key = _guest_session_key(request)
            if request.user.is_authenticated:
                guest_msg.sender_user = request.user
            guest_msg.save()
            messages.success(request, 'Your message was sent to the listing owner.')
            return redirect('guest_conversation', user_id=other_user.pk)
    else:
        initial = {}
        if request.user.is_authenticated:
            full_name = request.user.get_full_name().strip()
            initial = {
                'guest_name': full_name or request.user.username,
                'guest_email': request.user.email,
            }
        form = GuestMessageForm(initial=initial)

    return render(
        request,
        'chatapp/guest_conversation.html',
        {'other_user': other_user, 'form': form},
    )


def _guest_session_key(request):
    key = request.session.get('guest_chat_key')
    if not key:
        key = uuid.uuid4().hex
        request.session['guest_chat_key'] = key
    return key


@require_GET
def live_thread(request, user_id):
    other_user = get_object_or_404(User, pk=user_id)

    if request.user.is_authenticated:
        thread = ChatMessage.objects.filter(
            Q(sender=request.user, recipient=other_user)
            | Q(sender=other_user, recipient=request.user)
        ).order_by('sent_at')
        payload = [
            {
                'sender': msg.sender.username,
                'message': msg.message,
                'sent_at': msg.sent_at.strftime('%Y-%m-%d %H:%M:%S'),
                'mine': msg.sender_id == request.user.id,
            }
            for msg in thread
        ]
    else:
        guest_key = _guest_session_key(request)
        thread = GuestChatMessage.objects.filter(
            recipient=other_user,
            guest_session_key=guest_key,
        ).order_by('sent_at')
        payload = [
            {
                'sender': msg.guest_name,
                'message': msg.message,
                'sent_at': msg.sent_at.strftime('%Y-%m-%d %H:%M:%S'),
                'mine': True,
            }
            for msg in thread
        ]

    return JsonResponse({'messages': payload})


@require_POST
def live_send(request, user_id):
    other_user = get_object_or_404(User, pk=user_id)
    message_text = (request.POST.get('message') or '').strip()
    if not message_text:
        return JsonResponse({'error': 'Message cannot be empty.'}, status=400)

    if request.user.is_authenticated:
        if request.user.pk == other_user.pk:
            return JsonResponse({'error': 'You cannot message yourself.'}, status=400)
        msg = ChatMessage.objects.create(
            sender=request.user,
            recipient=other_user,
            message=message_text,
        )
        return JsonResponse(
            {
                'message': {
                    'sender': msg.sender.username,
                    'message': msg.message,
                    'sent_at': msg.sent_at.strftime('%Y-%m-%d %H:%M:%S'),
                    'mine': True,
                }
            },
            status=201,
        )

    guest_name = (request.POST.get('guest_name') or '').strip()
    guest_email = (request.POST.get('guest_email') or '').strip()
    if not guest_name or not guest_email:
        return JsonResponse({'error': 'Name and email are required for guests.'}, status=400)

    msg = GuestChatMessage.objects.create(
        recipient=other_user,
        sender_user=request.user if request.user.is_authenticated else None,
        guest_name=guest_name,
        guest_email=guest_email,
        message=message_text,
        guest_session_key=_guest_session_key(request),
    )
    return JsonResponse(
        {
            'message': {
                'sender': msg.guest_name,
                'message': msg.message,
                'sent_at': msg.sent_at.strftime('%Y-%m-%d %H:%M:%S'),
                'mine': True,
            }
        },
        status=201,
    )


# ── LISTING-SCOPED LIVE CHAT ──────────────────────────────────────────────


@require_GET
def listing_chat_thread(request, listing_id, other_user_id=None):
    """JSON: message thread for a listing.

    - Visitor (other_user_id=None): fetches their thread with the listing owner.
    - Owner  (other_user_id set):   fetches the thread with a specific visitor.
    """
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Login required.'}, status=401)

    listing = get_object_or_404(Listing, pk=listing_id)

    if other_user_id is not None:
        if request.user != listing.owner:
            return JsonResponse({'error': 'Forbidden.'}, status=403)
        other_user = get_object_or_404(User, pk=other_user_id)
    else:
        if request.user == listing.owner:
            return JsonResponse({'error': 'You own this listing.'}, status=400)
        other_user = listing.owner

    thread = ChatMessage.objects.filter(
        listing=listing,
    ).filter(
        Q(sender=request.user, recipient=other_user)
        | Q(sender=other_user, recipient=request.user)
    ).order_by('sent_at')

    payload = [
        {
            'sender': msg.sender.username,
            'message': msg.message,
            'sent_at': msg.sent_at.strftime('%H:%M'),
            'mine': msg.sender_id == request.user.id,
        }
        for msg in thread
    ]
    return JsonResponse({'messages': payload})


@require_POST
def listing_chat_send(request, listing_id, other_user_id=None):
    """Send a message tied to a listing."""
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Login required.'}, status=401)

    listing = get_object_or_404(Listing, pk=listing_id)

    if other_user_id is not None:
        if request.user != listing.owner:
            return JsonResponse({'error': 'Forbidden.'}, status=403)
        other_user = get_object_or_404(User, pk=other_user_id)
    else:
        if request.user == listing.owner:
            return JsonResponse({'error': 'You own this listing.'}, status=400)
        other_user = listing.owner

    message_text = (request.POST.get('message') or '').strip()
    if not message_text:
        return JsonResponse({'error': 'Message cannot be empty.'}, status=400)

    msg = ChatMessage.objects.create(
        listing=listing,
        sender=request.user,
        recipient=other_user,
        message=message_text,
    )
    return JsonResponse({
        'message': {
            'sender': msg.sender.username,
            'message': msg.message,
            'sent_at': msg.sent_at.strftime('%H:%M'),
            'mine': True,
        }
    }, status=201)


@login_required
def owner_chat(request, listing_id, other_user_id):
    """Full-page chat view: owner replies to a visitor's messages about a listing."""
    listing = get_object_or_404(Listing, pk=listing_id, owner=request.user)
    other_user = get_object_or_404(User, pk=other_user_id)

    thread = ChatMessage.objects.filter(
        listing=listing,
    ).filter(
        Q(sender=request.user, recipient=other_user)
        | Q(sender=other_user, recipient=request.user)
    ).order_by('sent_at')

    return render(request, 'chatapp/owner_chat.html', {
        'listing': listing,
        'other_user': other_user,
        'thread': thread,
    })
