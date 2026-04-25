from datetime import timedelta

from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Sum
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import redirect, render

from accounts.services.dashboard import owner_inquiries, owner_listing_overview, owner_performance, staff_agent_dashboard
from .forms import RegistrationForm
from listings.models import ListingInquiry


def register(request):
    if request.method == 'POST':
        form = RegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect('listing_list')
    else:
        form = RegistrationForm()
    return render(request, 'accounts/register.html', {'form': form})


@login_required
def profile(request):
    return render(request, 'accounts/profile.html', {})


@login_required
def my_listings(request):
    return render(request, 'accounts/my_listings.html', owner_listing_overview(request.user))


@login_required
def inquiries_overview(request):
    inquiries = owner_inquiries(request.user)
    unread_count = inquiries.filter(is_read=False).count()
    inquiries.filter(is_read=False).update(is_read=True)
    return render(request, 'accounts/inquiries_overview.html', {
        'inquiries':    inquiries,
        'unread_count': 0,
    })


@login_required
def performance(request):
    return render(request, 'accounts/performance.html', owner_performance(request.user))


@login_required
def agent_dashboard(request):
    if not request.user.is_staff:
        return HttpResponseForbidden()
    return render(request, 'accounts/agent_dashboard.html', staff_agent_dashboard(request.user))


@login_required
def unread_inquiry_count(request):
    return JsonResponse({
        'unread_count': ListingInquiry.objects.filter(
            listing__owner=request.user,
            is_read=False,
        ).count(),
    })
