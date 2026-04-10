from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render

from listings.models import ListingInquiry

from .forms import GuestMessageForm, MessageForm
from .models import ChatMessage, GuestChatMessage


@login_required
def inbox(request):
    users = User.objects.exclude(pk=request.user.pk)
    listing_inquiries = ListingInquiry.objects.filter(
        listing__owner=request.user
    ).select_related('listing')
    guest_messages = GuestChatMessage.objects.filter(recipient=request.user)
    return render(
        request,
        'chatapp/inbox.html',
        {
            'users': users,
            'listing_inquiries': listing_inquiries,
            'guest_messages': guest_messages,
        },
    )


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
