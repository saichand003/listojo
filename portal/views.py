from datetime import timedelta

from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.db.models import Count, Q, Sum
from django.db.models.functions import TruncDate
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from chatapp.models import ChatMessage
from listings.models import GuidedSearchEvent, Listing, ListingInquiry


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

    # ── Users ──────────────────────────────────────────────────
    total_users     = User.objects.count()
    new_users_7     = User.objects.filter(date_joined__gte=last_7).count()
    new_users_30    = User.objects.filter(date_joined__gte=last_30).count()
    recent_users    = User.objects.order_by('-date_joined')[:6]

    # ── Listings ───────────────────────────────────────────────
    total_listings  = Listing.objects.count()
    active_listings = Listing.objects.filter(status='active').count()
    new_listings_7  = Listing.objects.filter(created_at__gte=last_7).count()
    pending_count   = Listing.objects.filter(status='pending').count()
    flagged_count   = Listing.objects.filter(status='flagged').count()
    featured        = Listing.objects.filter(featured=True).count()
    total_views     = Listing.objects.aggregate(t=Sum('view_count'))['t'] or 0

    # ── Engagement ─────────────────────────────────────────────
    total_messages   = ChatMessage.objects.count()
    total_inquiries  = ListingInquiry.objects.count()
    new_inquiries_7  = ListingInquiry.objects.filter(created_at__gte=last_7).count()

    # ── Active listers (users with at least 1 active listing) ──
    active_listers = (
        User.objects.filter(listings__status='active')
        .distinct().count()
    )

    # ── Conversion funnel (5-step: visitors → agent) ───────────
    guided_starts    = GuidedSearchEvent.objects.filter(event_type=GuidedSearchEvent.START).count()
    guided_completes = GuidedSearchEvent.objects.filter(event_type=GuidedSearchEvent.COMPLETE).count()
    contacted_listers = ListingInquiry.objects.values('email').distinct().count()
    chat_conversations = ChatMessage.objects.values('listing').distinct().count()

    funnel_steps = [
        {'label': 'Visitors',              'count': total_views},
        {'label': 'Started guided search', 'count': guided_starts},
        {'label': 'Completed intake',      'count': guided_completes},
        {'label': 'Contacted a lister',    'count': contacted_listers},
        {'label': 'Connected to agent',    'count': chat_conversations},
    ]
    funnel_max = funnel_steps[0]['count'] or 1
    for s in funnel_steps:
        s['pct'] = round(s['count'] / funnel_max * 100) if funnel_max else 0

    # ── Search intent — bedroom-level for rentals when data exists ──
    total_active = active_listings or 1
    cat_map   = dict(Listing.CATEGORY_CHOICES)
    cat_icons = {
        'roommates': '🤝', 'rentals': '🏠', 'properties': '🏡',
        'local_services': '🔧', 'jobs': '💼', 'buy_sell': '🛍️', 'events': '🎉',
    }

    rentals_with_beds = Listing.objects.filter(
        status='active', category='rentals', bedrooms__isnull=False
    ).count()

    rental_rows = []
    if rentals_with_beds:
        # Show bedroom sub-breakdown
        for beds, label in [(2, 'Rentals — 2 bed'), (1, 'Rentals — 1 bed'), (3, 'Rentals — 3+ bed')]:
            q = (Listing.objects.filter(status='active', category='rentals', bedrooms__gte=3)
                 if beds == 3 else
                 Listing.objects.filter(status='active', category='rentals', bedrooms=beds))
            c = q.count()
            if c:
                rental_rows.append({'label': label, 'count': c,
                                     'pct': round(c / total_active * 100), 'icon': '🏠'})
        studio_count = Listing.objects.filter(status='active', category='rentals').filter(
            Q(property_type='studio') | Q(bedrooms=0)
        ).count()
        if studio_count:
            rental_rows.append({'label': 'Studios', 'count': studio_count,
                                 'pct': round(studio_count / total_active * 100), 'icon': '🏢'})
        exclude_rentals = True
    else:
        exclude_rentals = False  # show rentals as a whole category below

    # All categories (exclude rentals only when we have bedroom breakdown above)
    other_rows = []
    qs = Listing.objects.filter(status='active').values('category').annotate(total=Count('id')).order_by('-total')
    if exclude_rentals:
        qs = qs.exclude(category='rentals')
    for r in qs:
        other_rows.append({
            'label': cat_map.get(r['category'], r['category']),
            'count': r['total'],
            'pct':   round(r['total'] / total_active * 100),
            'icon':  cat_icons.get(r['category'], '📋'),
        })

    category_data = sorted(rental_rows + other_rows, key=lambda x: -x['count'])[:6]

    # ── Top city by listing views ───────────────────────────────
    top_city_row = (
        Listing.objects.filter(status='active')
        .values('city')
        .annotate(city_views=Sum('view_count'))
        .order_by('-city_views')
        .first()
    )
    top_city     = top_city_row['city'] if top_city_row else None
    top_city_pct = round(top_city_row['city_views'] / (total_views or 1) * 100) if top_city_row and top_city_row['city_views'] else 0

    # ── Top listers ─────────────────────────────────────────────
    top_listers = list(
        User.objects
        .annotate(
            lv=Sum('listings__view_count'),
            lc=Count('listings', filter=Q(listings__status='active'), distinct=True),
            iq=Count('listings__inquiries', distinct=True),
        )
        .filter(lc__gt=0)
        .order_by('-lv')[:5]
    )

    # ── Listings needing review (pending first, then flagged) ───
    review_listings = (
        Listing.objects.select_related('owner')
        .filter(Q(status='pending') | Q(status='flagged'))
        .order_by('-created_at')[:10]
    )

    # ── Quality issues ──────────────────────────────────────────
    no_photos   = (
        Listing.objects.filter(status='active')
        .annotate(img_count=Count('images'))
        .filter(img_count=0).count()
    )
    no_tags     = Listing.objects.filter(status='active', tags='').count()
    stale       = (
        Listing.objects.filter(
            status='active',
            created_at__lte=now - timedelta(days=14),
            view_count__lt=3,
        ).count()
    )

    return render(request, 'portal/dashboard.html', {
        # Users
        'total_users':      total_users,
        'new_users_7':      new_users_7,
        'new_users_30':     new_users_30,
        'recent_users':     recent_users,
        # Listings
        'total_listings':   total_listings,
        'active_listings':  active_listings,
        'new_listings_7':   new_listings_7,
        'pending_count':    pending_count,
        'flagged_count':    flagged_count,
        'featured':         featured,
        'total_views':      total_views,
        # Engagement
        'total_messages':   total_messages,
        'total_inquiries':  total_inquiries,
        'new_inquiries_7':  new_inquiries_7,
        'active_listers':   active_listers,
        # Funnel
        'funnel_steps':     funnel_steps,
        # Categories
        'category_data':    category_data,
        'top_city':         top_city,
        'top_city_pct':     top_city_pct,
        # Top listers
        'top_listers':      top_listers,
        # Review queue
        'review_listings':  review_listings,
        # Quality
        'no_photos':        no_photos,
        'no_tags':          no_tags,
        'stale':            stale,
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


