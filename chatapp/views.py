import uuid

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_POST

from listings.models import Listing, ListingInquiry
from chatapp.services.inbox_service import build_listing_conversations
from chatapp.services.lead_service import maybe_create_chat_lead
from chatapp.services.typing_state import is_user_typing, set_typing_state

from .forms import GuestMessageForm, MessageForm
from .models import ChatMessage, GuestChatMessage


@login_required
def inbox(request):
    listing_conversations = build_listing_conversations(request.user)
    return render(request, 'chatapp/inbox.html', {
        'listing_conversations': listing_conversations,
    })


@login_required
def unread_count(request):
    return JsonResponse({
        'unread_count': ChatMessage.objects.filter(
            recipient=request.user,
            is_read=False,
        ).count(),
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
        other_user = get_object_or_404(User, pk=other_user_id)
        if request.user != listing.owner and not ChatMessage.objects.filter(
            listing=listing,
        ).filter(
            Q(sender=request.user, recipient=other_user)
            | Q(sender=other_user, recipient=request.user)
        ).exists():
            return JsonResponse({'error': 'Forbidden.'}, status=403)
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

    # Mark incoming messages as read
    ChatMessage.objects.filter(
        listing=listing,
        sender=other_user,
        recipient=request.user,
        is_read=False,
    ).update(is_read=True)

    payload = [
        {
            'sender': msg.sender.username,
            'message': msg.message,
            'sent_at': msg.sent_at.strftime('%H:%M'),
            'mine': msg.sender_id == request.user.id,
            'is_read': msg.is_read,
        }
        for msg in thread
    ]
    return JsonResponse({
        'messages': payload,
        'other_user_typing': is_user_typing(listing.pk, other_user.pk, request.user.pk),
    })


@require_POST
def listing_chat_send(request, listing_id, other_user_id=None):
    """Send a message tied to a listing."""
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Login required.'}, status=401)

    listing = get_object_or_404(Listing, pk=listing_id)

    if other_user_id is not None:
        other_user = get_object_or_404(User, pk=other_user_id)
        if request.user != listing.owner and not ChatMessage.objects.filter(
            listing=listing,
        ).filter(
            Q(sender=request.user, recipient=other_user)
            | Q(sender=other_user, recipient=request.user)
        ).exists():
            return JsonResponse({'error': 'Forbidden.'}, status=403)
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
    set_typing_state(listing.pk, request.user.pk, other_user.pk, False)

    # Capture demand signal: create lead on visitor's first message
    if request.user != listing.owner:
        maybe_create_chat_lead(request.user, listing)

    return JsonResponse({
        'message': {
            'sender': msg.sender.username,
            'message': msg.message,
            'sent_at': msg.sent_at.strftime('%H:%M'),
            'mine': True,
        }
    }, status=201)


@require_POST
def listing_chat_typing(request, listing_id, other_user_id=None):
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Login required.'}, status=401)

    listing = get_object_or_404(Listing, pk=listing_id)

    if other_user_id is not None:
        other_user = get_object_or_404(User, pk=other_user_id)
        if request.user != listing.owner and not ChatMessage.objects.filter(
            listing=listing,
        ).filter(
            Q(sender=request.user, recipient=other_user)
            | Q(sender=other_user, recipient=request.user)
        ).exists():
            return JsonResponse({'error': 'Forbidden.'}, status=403)
    else:
        if request.user == listing.owner:
            return JsonResponse({'error': 'You own this listing.'}, status=400)
        other_user = listing.owner

    is_typing = (request.POST.get('is_typing') or '').lower() == 'true'
    set_typing_state(listing.pk, request.user.pk, other_user.pk, is_typing)
    return JsonResponse({'ok': True, 'is_typing': is_typing})


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
