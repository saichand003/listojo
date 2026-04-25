from django.contrib.auth import authenticate, login, logout
from django.views.decorators.http import require_POST
from django.contrib.auth.models import User
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render

from chatapp.models import ChatMessage
from chatapp.services.inbox_service import build_listing_conversations
from listings.models import Listing
from listings.services.lifecycle import approve as approve_listing_service
from listings.services.lifecycle import flag as flag_listing_service
from listings.services.lifecycle import reject as reject_listing_service
from listings.services.lifecycle import toggle_featured as toggle_featured_service
from listings.services.visibility import active_listings as visible_listings
from .models import Lead, Shortlist
from .services.dashboard import build_admin_dashboard_context
from .services.clients import build_client_profile, build_client_summaries
from .services.routing import assign_to_agent, least_loaded_agent
from .services.shortlist_service import (
    build_curated,
    build_manual_listing_pool,
    create_and_send,
    create_shortlist,
    generate_conversion_tip,
    send_shortlist,
)


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
    return render(request, 'portal/dashboard.html', build_admin_dashboard_context())


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
        toggle_featured_service(listing)
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
        approve_listing_service(listing)
    return redirect(request.POST.get('next', 'portal_listings'))


@portal_login_required
def reject_listing(request, pk):
    if request.method == 'POST':
        listing = get_object_or_404(Listing, pk=pk)
        reject_listing_service(listing)
    return redirect(request.POST.get('next', 'portal_listings'))


@portal_login_required
def flag_listing(request, pk):
    if request.method == 'POST':
        listing = get_object_or_404(Listing, pk=pk)
        flag_listing_service(listing)
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
def _build_leads_data(leads_qs):
    """Enrich a lead queryset with matched listing count and preference summary."""
    result = []
    for lead in leads_qs.prefetch_related('shortlists'):
        pref = getattr(lead, 'preference', None)
        matched_count = 0
        pref_summary_parts = []
        if pref:
            qs = visible_listings()
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
    scope  = request.GET.get('scope', '').strip()

    if request.user.is_superuser:
        qs = Lead.objects.select_related('assigned_agent', 'listing', 'preference')
    else:
        qs = Lead.objects.filter(assigned_agent=agent).select_related('assigned_agent', 'listing', 'preference')

    if scope == 'clients':
        qs = qs.filter(status__in=[
            'contacted',
            'shortlist_ready',
            'shortlist_sent',
            'touring',
            'application_in_progress',
        ])
        if status:
            qs = qs.filter(status=status)
    elif status:
        qs = qs.filter(status=status)
    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(email__icontains=q))

    leads_data = _build_leads_data(qs)

    return render(request, 'portal/agent_leads.html', {
        'leads_data':     leads_data,
        'status_filter':  status,
        'scope':          scope,
        'q':              q,
        'status_choices': Lead.STATUS_CHOICES,
        'all_agents':     User.objects.filter(is_staff=True) if request.user.is_superuser else None,
    })


@agent_login_required
def agent_messages(request):
    return render(request, 'portal/agent_messages.html', {
        'listing_conversations': build_listing_conversations(request.user),
    })


@agent_login_required
def agent_clients(request):
    return render(request, 'portal/agent_clients.html', {
        'clients': build_client_summaries(request.user),
    })


@agent_login_required
def agent_client_detail(request, email):
    profile = build_client_profile(request.user, email)
    if profile is None:
        return redirect('agent_clients')
    return render(request, 'portal/agent_client_detail.html', profile)


@agent_login_required
def agent_lead_detail(request, pk):
    if request.user.is_superuser:
        lead = get_object_or_404(Lead.objects.select_related('assigned_agent', 'listing'), pk=pk)
    else:
        lead = get_object_or_404(Lead.objects.select_related('assigned_agent', 'listing'),
                                  pk=pk, assigned_agent=request.user)

    shortlists = lead.shortlists.prefetch_related('items__listing').order_by('-created_at')
    preference = getattr(lead, 'preference', None)
    curated = build_curated(lead)
    conversion_tip = generate_conversion_tip(curated, preference) if curated else None
    curated_ids = {item['listing'].pk for item in curated}
    manual_listings = build_manual_listing_pool(lead, curated_ids)

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
            lead.save(update_fields=['assigned_agent', 'updated_at'])
        elif action == 'create_shortlist':
            listing_ids = request.POST.getlist('listing_ids')
            if listing_ids:
                create_shortlist(lead, request.user, [int(lid) for lid in listing_ids if str(lid).isdigit()])
        elif action == 'send_curated_shortlist':
            top_ids = request.POST.getlist('curated_ids')
            if top_ids:
                create_and_send(lead, request.user, [int(lid) for lid in top_ids if str(lid).isdigit()])
        elif action == 'mark_sent':
            sl_id = request.POST.get('shortlist_id')
            shortlist = get_object_or_404(Shortlist, pk=sl_id, lead=lead)
            send_shortlist(shortlist)
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

    qs = visible_listings()
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

    agent = least_loaded_agent()
    if not agent:
        return JsonResponse({'error': 'No agents available right now.'}, status=503)

    assign_to_agent(lead, agent)
    request.session.pop('gs_lead_id', None)

    return JsonResponse({'ok': True, 'agent': agent.get_full_name() or agent.username})
