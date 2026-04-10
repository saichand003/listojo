from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render

from listings.models import ListingInquiry

from .forms import MessageForm
from .models import ChatMessage


@login_required
def inbox(request):
    users = User.objects.exclude(pk=request.user.pk)
    listing_inquiries = ListingInquiry.objects.filter(
        listing__owner=request.user
    ).select_related('listing')
    return render(
        request,
        'chatapp/inbox.html',
        {'users': users, 'listing_inquiries': listing_inquiries},
    )


@login_required
def conversation(request, user_id):
    other_user = get_object_or_404(User, pk=user_id)
    messages = ChatMessage.objects.filter(
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
        {'other_user': other_user, 'messages': messages, 'form': form},
    )
