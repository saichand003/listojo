from datetime import timedelta
from datetime import date as _date

from django.contrib.auth import authenticate, login, logout
from django.views.decorators.http import require_POST
from django.contrib.auth.models import User
from django.db import models as django_models
from django.db.models import Count, Q, Sum
from django.db.models.functions import TruncDate
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from chatapp.models import ChatMessage
from listings.models import GuidedSearchEvent, Listing, ListingInquiry
from .models import Lead, LeadPreference, Shortlist, ShortlistItem


def portal_login_required(view_fn):
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated or not request.user.is_superuser:
            return redirect('portal_login')
        return view_fn(request, *args, **kwargs)
    wrapper.__name__ = view_fn.__name__
    return wrapper


def agent_login_required(view_fn):
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated or not (request.user.is_staff or request.user.is_superuser):
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


@portal_login_required
def agents_view(request):
    agents = (
        User.objects.filter(is_staff=True)
        .annotate(
            listing_count=Count('listings', distinct=True),
            lead_count=Count('assigned_leads', distinct=True),
        )
        .order_by('-date_joined')
    )
    return render(request, 'portal/agents.html', {'agents': agents})


# ── AGENT PORTAL ─────────────────────────────────────────────────────────────

def _compute_listing_match(listing, preference):
    """Return (match_pct, reasons, caveats) for a listing vs a LeadPreference."""
    reasons, caveats, score = [], [], 70

    if preference.max_budget and listing.price:
        budget = float(preference.max_budget)
        price  = float(listing.price)
        if price <= budget * 0.93:
            reasons.append('Under budget')
            score += 8
        elif price <= budget:
            caveats.append('At budget max')
            score += 2
        else:
            score -= 8

    if preference.bedrooms and listing.bedrooms:
        if listing.bedrooms == preference.bedrooms:
            reasons.append(f'{listing.bedrooms} bed match')
            score += 6

    if preference.amenities and listing.tags:
        pref_set = {a.strip().lower() for a in preference.amenities.split(',') if a.strip()}
        tags_lower = listing.tags.lower()
        tag_labels = {
            'pet friendly': 'Pet friendly', 'washer dryer': 'W/D in unit',
            'washer/dryer': 'W/D in unit',  'parking': 'Parking',
            'central ac': 'Central AC',     'gym': 'Gym',
            'pool': 'Pool',                 'furnished': 'Furnished',
            'bills included': 'Bills included', 'gated': 'Gated',
            'balcony': 'Balcony',           'high-speed internet': 'High-speed internet',
        }
        for amenity in pref_set:
            if amenity in tags_lower or any(w in tags_lower for w in amenity.split()):
                label = tag_labels.get(amenity, amenity.replace('_', ' ').title())
                if label not in reasons:
                    reasons.append(label)
                    score += 3

    return max(65, min(98, score)), reasons[:4], caveats[:2]


def _generate_conversion_tip(curated, preference):
    """Generate a short agent tip based on top match and preferences."""
    if not curated:
        return None
    top = curated[0]
    listing = top['listing']
    tips = []
    if 'Under budget' in top['reasons'] and preference.max_budget and listing.price:
        savings = int(float(preference.max_budget) - float(listing.price))
        tips.append(f"Lead with the ${savings:,}/mo savings vs their budget")
    if 'Pet friendly' in top['reasons']:
        tips.append("pet-friendly angle is a strong differentiator")
    if preference.amenities:
        top_amenity = preference.amenities.split(',')[0].strip().title()
        if top_amenity and top_amenity.lower() not in ['under budget', 'pet friendly']:
            tips.append(f"{top_amenity} is a stated must-have — confirm it's available")
    if not tips:
        tips.append(f"{listing.city} area matches their target location")
    return f"{listing.title[:28]}… is your strongest lead — {tips[0]}."


def _build_leads_data(leads_qs):
    """Enrich a lead queryset with matched listing count and preference summary."""
    result = []
    for lead in leads_qs.prefetch_related('shortlists'):
        pref = getattr(lead, 'preference', None)
        matched_count = 0
        pref_summary_parts = []
        if pref:
            today = _date.today()
            qs = Listing.objects.filter(status='active').filter(
                Q(expires_at__isnull=True) | Q(expires_at__gte=today)
            )
            if pref.city:
                qs = qs.filter(city__icontains=pref.city)
                pref_summary_parts.append(pref.city)
            if pref.bedrooms:
                qs = qs.filter(bedrooms=pref.bedrooms)
                pref_summary_parts.append(f'{pref.bedrooms} bed')
            if pref.max_budget:
                qs = qs.filter(price__lte=pref.max_budget)
                pref_summary_parts.append(f'Under ${int(pref.max_budget):,}')
            if pref.amenities:
                pref_summary_parts.append(pref.amenities.split(',')[0].strip().title())
            if pref.move_in_date:
                pref_summary_parts.append(pref.move_in_date.strftime('%b %Y'))
            matched_count = qs.count()
        elif lead.listing:
            pref_summary_parts.append(lead.listing.city)

        # Simple match score: % of filled preference criteria
        criteria = ['city', 'bedrooms', 'max_budget', 'amenities', 'move_in_date']
        filled = sum(1 for c in criteria if pref and getattr(pref, c, None))
        match_pct = max(70, min(98, 70 + filled * 6)) if filled else 0

        result.append({
            'lead':          lead,
            'preference':    pref,
            'pref_summary':  ' · '.join(pref_summary_parts),
            'matched_count': matched_count,
            'match_pct':     match_pct,
        })
    return result


@agent_login_required
def agent_dashboard(request):
    agent        = request.user
    status_filter = request.GET.get('status', '').strip()
    my_leads     = Lead.objects.filter(assigned_agent=agent).select_related('listing', 'preference')

    total         = my_leads.count()
    new_count     = my_leads.filter(status='new').count()
    active_count  = my_leads.filter(status__in=['contacted', 'shortlist_ready',
                                                 'shortlist_sent', 'touring',
                                                 'application_in_progress']).count()
    won_count     = my_leads.filter(status='closed_won').count()
    lost_count    = my_leads.filter(status='closed_lost').count()
    shortlists_sent = Shortlist.objects.filter(agent=agent, status__in=['sent', 'viewed']).count()

    display_qs = my_leads
    if status_filter:
        display_qs = display_qs.filter(status=status_filter)

    leads_data = _build_leads_data(display_qs[:10])

    return render(request, 'portal/agent_dashboard.html', {
        'total':           total,
        'new_count':       new_count,
        'active_count':    active_count,
        'won_count':       won_count,
        'lost_count':      lost_count,
        'shortlists_sent': shortlists_sent,
        'leads_data':      leads_data,
        'status_filter':   status_filter,
    })


@agent_login_required
def agent_leads(request):
    agent  = request.user
    status = request.GET.get('status', '').strip()
    q      = request.GET.get('q', '').strip()

    if request.user.is_superuser:
        qs = Lead.objects.select_related('assigned_agent', 'listing', 'preference')
    else:
        qs = Lead.objects.filter(assigned_agent=agent).select_related('assigned_agent', 'listing', 'preference')

    if status:
        qs = qs.filter(status=status)
    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(email__icontains=q))

    leads_data = _build_leads_data(qs)

    return render(request, 'portal/agent_leads.html', {
        'leads_data':     leads_data,
        'status_filter':  status,
        'q':              q,
        'status_choices': Lead.STATUS_CHOICES,
        'all_agents':     User.objects.filter(is_staff=True) if request.user.is_superuser else None,
    })


@agent_login_required
def agent_lead_detail(request, pk):
    if request.user.is_superuser:
        lead = get_object_or_404(Lead.objects.select_related('assigned_agent', 'listing'), pk=pk)
    else:
        lead = get_object_or_404(Lead.objects.select_related('assigned_agent', 'listing'),
                                  pk=pk, assigned_agent=request.user)

    shortlists  = lead.shortlists.prefetch_related('items__listing').order_by('-created_at')
    preference  = getattr(lead, 'preference', None)

    # Build curated shortlist with match scores
    today = _date.today()
    already_shortlisted = {i.listing_id for sl in shortlists for i in sl.items.all()}
    curated = []
    if preference and preference.city:
        qs = (
            Listing.objects.filter(status='active', city__icontains=preference.city)
            .filter(Q(expires_at__isnull=True) | Q(expires_at__gte=today))
            .exclude(id__in=already_shortlisted)
        )
        if preference.bedrooms:
            qs = qs.filter(bedrooms=preference.bedrooms)
        if preference.max_budget:
            qs = qs.filter(price__lte=float(preference.max_budget) * 1.1)
        for listing in qs[:12]:
            pct, reasons, caveats = _compute_listing_match(listing, preference)
            curated.append({'listing': listing, 'match_pct': pct,
                            'reasons': reasons, 'caveats': caveats})
        curated.sort(key=lambda x: -x['match_pct'])
        curated = curated[:6]

    conversion_tip = _generate_conversion_tip(curated, preference) if curated else None

    # Broader listing pool for manual selection (city only, no budget/bedroom filter)
    curated_ids = {item['listing'].pk for item in curated}
    manual_listings = []
    if preference and preference.city:
        manual_listings = list(
            Listing.objects.filter(status='active', city__icontains=preference.city)
            .filter(Q(expires_at__isnull=True) | Q(expires_at__gte=today))
            .exclude(id__in=already_shortlisted)
            .order_by('-featured', '-created_at')[:30]
        )
    elif lead.listing:
        manual_listings = list(
            Listing.objects.filter(status='active', city__icontains=lead.listing.city)
            .filter(Q(expires_at__isnull=True) | Q(expires_at__gte=today))
            .exclude(id__in=already_shortlisted)
            .order_by('-featured', '-created_at')[:30]
        )

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'update_status':
            new_status = request.POST.get('status')
            if new_status in [s[0] for s in Lead.STATUS_CHOICES]:
                lead.status = new_status
                lead.save()
        elif action == 'save_note':
            lead.notes = request.POST.get('notes', '')
            lead.save()
        elif action == 'assign_agent' and request.user.is_superuser:
            agent_id = request.POST.get('agent_id', '').strip()
            lead.assigned_agent = get_object_or_404(User, pk=agent_id, is_staff=True) if agent_id else None
            lead.save()
        elif action == 'create_shortlist':
            listing_ids = request.POST.getlist('listing_ids')
            if listing_ids:
                sl = Shortlist.objects.create(lead=lead, agent=request.user)
                for idx, lid in enumerate(listing_ids):
                    try:
                        listing = Listing.objects.get(pk=lid, status='active')
                        ShortlistItem.objects.create(shortlist=sl, listing=listing, order_index=idx)
                    except Listing.DoesNotExist:
                        pass
        elif action == 'send_curated_shortlist':
            # Create shortlist from top curated matches and mark sent immediately
            top_ids = request.POST.getlist('curated_ids')
            if top_ids:
                sl = Shortlist.objects.create(lead=lead, agent=request.user,
                                              status='sent', sent_at=timezone.now())
                for idx, lid in enumerate(top_ids):
                    try:
                        listing = Listing.objects.get(pk=lid, status='active')
                        ShortlistItem.objects.create(shortlist=sl, listing=listing, order_index=idx)
                    except Listing.DoesNotExist:
                        pass
                lead.status = 'shortlist_sent'
                lead.save()
        elif action == 'mark_sent':
            sl_id = request.POST.get('shortlist_id')
            sl    = get_object_or_404(Shortlist, pk=sl_id, lead=lead)
            sl.status  = 'sent'
            sl.sent_at = timezone.now()
            sl.save()
        return redirect('agent_lead_detail', pk=lead.pk)

    return render(request, 'portal/agent_lead_detail.html', {
        'lead':            lead,
        'shortlists':      shortlists,
        'preference':      preference,
        'curated':          curated,
        'curated_ids':      curated_ids,
        'manual_listings':  manual_listings,
        'conversion_tip':   conversion_tip,
        'status_choices':   Lead.STATUS_CHOICES,
        'all_agents':       User.objects.filter(is_staff=True) if request.user.is_superuser else None,
    })


@agent_login_required
def listing_search_api(request):
    """JSON search for active listings — used by the manual shortlist builder."""
    q = request.GET.get('q', '').strip()
    if not q or len(q) < 2:
        return JsonResponse({'results': []})

    today = _date.today()
    qs = Listing.objects.filter(status='active').filter(
        Q(expires_at__isnull=True) | Q(expires_at__gte=today)
    )
    if q.isdigit():
        qs = qs.filter(pk=int(q))
    else:
        qs = qs.filter(Q(title__icontains=q) | Q(city__icontains=q))

    results = []
    for listing in qs.select_related('owner')[:12]:
        thumb = None
        first_img = listing.images.first()
        if first_img:
            thumb = first_img.image.url
        results.append({
            'id':         listing.pk,
            'title':      listing.title,
            'city':       listing.city,
            'price':      str(listing.price) if listing.price else '',
            'price_unit': listing.price_unit or '',
            'bedrooms':   listing.bedrooms,
            'thumb':      thumb,
        })
    return JsonResponse({'results': results})


@require_POST
def request_agent(request):
    """User opts in to agent help — assigns their unassigned guided-search lead."""
    lead_id = request.session.get('gs_lead_id')
    if not lead_id:
        return JsonResponse({'error': 'No active search session.'}, status=400)

    try:
        lead = Lead.objects.get(pk=lead_id, assigned_agent__isnull=True)
    except Lead.DoesNotExist:
        # Already assigned or invalid — clear session and continue
        request.session.pop('gs_lead_id', None)
        return JsonResponse({'ok': True, 'already_assigned': True})

    agent = (
        User.objects.filter(is_staff=True, is_active=True)
        .annotate(open_leads=django_models.Count(
            'assigned_leads',
            filter=django_models.Q(assigned_leads__status__in=[
                'new', 'contacted', 'shortlist_ready', 'shortlist_sent',
                'touring', 'application_in_progress',
            ])
        ))
        .order_by('open_leads', 'id')
        .first()
    )

    if not agent:
        return JsonResponse({'error': 'No agents available right now.'}, status=503)

    lead.assigned_agent = agent
    lead.save()
    request.session.pop('gs_lead_id', None)

    return JsonResponse({'ok': True, 'agent': agent.get_full_name() or agent.username})
