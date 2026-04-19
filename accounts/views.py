from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.db.models import Count
from django.shortcuts import redirect, render

from .forms import RegistrationForm
from listings.models import Listing


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
    my_listings = (
        Listing.objects
        .filter(owner=request.user)
        .annotate(
            inquiry_count=Count('inquiries', distinct=True),
            save_count=Count('favourited_by', distinct=True),
        )
        .order_by('-created_at')
    )
    active_count = my_listings.filter(status='active').count()
    draft_count  = my_listings.filter(status='draft').count()
    return render(request, 'accounts/profile.html', {
        'my_listings':   my_listings,
        'active_count':  active_count,
        'draft_count':   draft_count,
    })
