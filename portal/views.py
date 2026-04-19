from datetime import timedelta

from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.db.models import Count, Q
from django.db.models.functions import TruncDate
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from chatapp.models import ChatMessage
from listings.models import Listing, ListingInquiry


def portal_login_required(view_fn):
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated or not request.user.is_superuser:
            return redirect('portal_login')
        return view_fn(request, *args, **kwargs)
    wrapper.__name__ = view_fn.__name__
    return wrapper


def portal_login(request):
    if request.user.is_authenticated and request.user.is_superuser:
        return redirect('portal_dashboard')
    error = None
    if request.method == 'POST':
        user = authenticate(request,
                            username=request.POST.get('username'),
                            password=request.POST.get('password'))
        if user and user.is_superuser:
            logout(request)          # clear any existing regular-user session
            login(request, user)
            return redirect('portal_dashboard')
        error = 'Invalid credentials or insufficient permissions.'
    return render(request, 'portal/login.html', {'error': error})


def portal_logout(request):
    logout(request)
    return redirect('portal_login')


@portal_login_required
def dashboard(request):
    now = timezone.now()
    last_7  = now - timedelta(days=7)
    last_30 = now - timedelta(days=30)

    total_users     = User.objects.count()
    new_users_7     = User.objects.filter(date_joined__gte=last_7).count()
    new_users_30    = User.objects.filter(date_joined__gte=last_30).count()

    total_listings  = Listing.objects.count()
    featured        = Listing.objects.filter(featured=True).count()
    new_listings_7  = Listing.objects.filter(created_at__gte=last_7).count()
    pending_count   = Listing.objects.filter(status='pending').count()
    flagged_count   = Listing.objects.filter(status='flagged').count()

    total_messages  = ChatMessage.objects.count()
    total_inquiries = ListingInquiry.objects.count()

    cat_map = dict(Listing.CATEGORY_CHOICES)
    by_category = (
        Listing.objects.values('category')
        .annotate(total=Count('id'))
        .order_by('-total')
    )
    category_data = [
        {'label': cat_map.get(r['category'], r['category']), 'count': r['total']}
        for r in by_category
    ]

    listings_trend = list(
        Listing.objects.filter(created_at__gte=now - timedelta(days=14))
        .annotate(day=TruncDate('created_at'))
        .values('day')
        .annotate(count=Count('id'))
        .order_by('day')
    )

    recent_listings = (
        Listing.objects.select_related('owner')
        .filter(Q(status='pending') | Q(status='flagged') | Q(status='active'))
        .order_by('-created_at')[:8]
    )
    recent_users    = User.objects.order_by('-date_joined')[:8]

    return render(request, 'portal/dashboard.html', {
        'total_users':    total_users,
        'new_users_7':    new_users_7,
        'new_users_30':   new_users_30,
        'total_listings': total_listings,
        'featured':       featured,
        'new_listings_7': new_listings_7,
        'pending_count':  pending_count,
        'flagged_count':  flagged_count,
        'total_messages': total_messages,
        'total_inquiries':total_inquiries,
        'category_data':  category_data,
        'listings_trend': listings_trend,
        'recent_listings':recent_listings,
        'recent_users':   recent_users,
    })


@portal_login_required
def users_view(request):
    q  = request.GET.get('q', '').strip()
    qs = User.objects.order_by('-date_joined').annotate(listing_count=Count('listings'))
    if q:
        qs = qs.filter(Q(username__icontains=q) | Q(email__icontains=q))
    return render(request, 'portal/users.html', {'users': qs, 'q': q})


@portal_login_required
def user_detail(request, pk):
    u        = get_object_or_404(User, pk=pk)
    listings = Listing.objects.filter(owner=u).order_by('-created_at')
    return render(request, 'portal/user_detail.html', {'u': u, 'listings': listings})


@portal_login_required
def toggle_user_active(request, pk):
    if request.method == 'POST':
        u = get_object_or_404(User, pk=pk)
        if not u.is_superuser:          # never deactivate other admins
            u.is_active = not u.is_active
            u.save()
    return redirect('portal_users')


@portal_login_required
def listings_view(request):
    q             = request.GET.get('q', '').strip()
    category      = request.GET.get('category', '').strip()
    status_filter = request.GET.get('status', '').strip()
    qs = Listing.objects.select_related('owner').order_by('-created_at')
    if q:
        qs = qs.filter(Q(title__icontains=q) | Q(owner__username__icontains=q))
    if category:
        qs = qs.filter(category=category)
    if status_filter:
        qs = qs.filter(status=status_filter)
    return render(request, 'portal/listings.html', {
        'listings':         qs,
        'q':                q,
        'category':         category,
        'status_filter':    status_filter,
        'category_choices': Listing.CATEGORY_CHOICES,
    })


@portal_login_required
def toggle_featured(request, pk):
    if request.method == 'POST':
        listing = get_object_or_404(Listing, pk=pk)
        listing.featured = not listing.featured
        listing.save()
    return redirect('portal_listings')


@portal_login_required
def delete_listing(request, pk):
    if request.method == 'POST':
        get_object_or_404(Listing, pk=pk).delete()
    return redirect('portal_listings')


@portal_login_required
def approve_listing(request, pk):
    if request.method == 'POST':
        listing = get_object_or_404(Listing, pk=pk)
        listing.status = 'active'
        listing.save()
    return redirect(request.POST.get('next', 'portal_listings'))


@portal_login_required
def reject_listing(request, pk):
    if request.method == 'POST':
        listing = get_object_or_404(Listing, pk=pk)
        listing.status = 'draft'
        listing.save()
    return redirect(request.POST.get('next', 'portal_listings'))


@portal_login_required
def flag_listing(request, pk):
    if request.method == 'POST':
        listing = get_object_or_404(Listing, pk=pk)
        listing.status = 'flagged'
        listing.save()
    return redirect(request.POST.get('next', 'portal_listings'))


@portal_login_required
def agents_view(request):
    agents = (
        User.objects
        .filter(is_staff=True, is_superuser=False)
        .annotate(listing_count=Count('listings'))
        .order_by('-date_joined')
    )
    return render(request, 'portal/agents.html', {'agents': agents})
