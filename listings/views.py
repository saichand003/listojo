from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.mail import send_mail
from django.db import connection
from django.db.utils import OperationalError
from django.db import models as django_models
from django.db.models import Case, Count, IntegerField, Q, Sum, Value, When
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from datetime import timedelta, date

from .forms import ListingForm, ListingInquiryForm, validate_uploaded_images
from .models import CityWaitlist, Favourite, GuidedSearchEvent, Listing, ListingImage
from portal.models import Lead, LeadPreference


def _fmm_score(listing, max_price_val, requested_tags, avail_date,
               accommodation_type='', property_type=''):
    """
    Return (pct: int 0-100, reasons: list[str], tag_hits: int).
    Scores are always relative to what the user asked for.
    Missing criteria lower the score but never zero it out — users always see results.
    """
    pts, max_pts = 0, 0
    reasons = []
    tag_hits = 0
    tags_lower = (listing.tags or '').lower()

    # ── Budget (40 pts) — most important criterion ───────────────────────
    if max_price_val and max_price_val > 0:
        max_pts += 40
        if listing.price:
            price = float(listing.price)
            effective = price - (150 if listing.bills_included else 0)
            headroom = float(max_price_val) - effective
            if headroom >= 0:
                ratio = headroom / float(max_price_val)
                pts += 30 + min(10, int(ratio * 20))
                if listing.bills_included:
                    reasons.append(f"Bills included (effective ~${int(effective):,}/mo)")
                elif headroom >= 500:
                    reasons.append(f"${int(headroom):,} under budget")
                elif headroom >= 100:
                    reasons.append(f"${int(headroom):,} under budget")
                else:
                    reasons.append("Within budget")
            elif headroom >= -float(max_price_val) * 0.10:
                pts += 12  # just over budget, small partial credit
            # else: well over budget — 0 pts
        else:
            pts += 20  # no price listed — neutral

    # ── Accommodation type match (15 pts) ────────────────────────────────
    if accommodation_type:
        max_pts += 15
        if listing.accommodation_type == accommodation_type:
            pts += 15
            label = 'Whole place' if accommodation_type == 'whole' else 'Single room'
            reasons.append(label)
        # No match — 0 pts, but listing still surfaces with lower score

    # ── Property type match (10 pts) ─────────────────────────────────────
    if property_type:
        max_pts += 10
        if listing.property_type == property_type:
            pts += 10
            reasons.append(listing.get_property_type_display())

    # ── Tag matches (15 pts each, partial credit for related tags) ───────
    if requested_tags:
        for tag in requested_tags:
            max_pts += 15
            tag_l = tag.lower()
            if tag_l in tags_lower:
                pts += 15
                tag_hits += 1
                reasons.append(tag)
            else:
                # Partial credit for semantically related tags
                related = {
                    'garage': ['parking', 'covered parking', 'carport'],
                    'lake': ['waterway', 'water view', 'canal', 'pond', 'pool'],
                    'pool': ['gym', 'amenities', 'community pool'],
                    'gym': ['fitness', 'workout', 'exercise'],
                    'pet friendly': ['pet-friendly', 'pets allowed', 'dogs ok'],
                    'furnished': ['fully furnished', 'semi-furnished'],
                    'balcony': ['patio', 'terrace', 'deck', 'outdoor'],
                    'gated': ['secured', 'secure', 'fenced'],
                    'schools': ['near schools', 'good schools', 'school district'],
                }
                close = related.get(tag_l, [])
                if any(r in tags_lower for r in close):
                    pts += 5  # partial credit
                    reasons.append(f"Similar to {tag}")

    # ── Availability (10 pts) ────────────────────────────────────────────
    if avail_date:
        max_pts += 10
        if not listing.available_from or listing.available_from <= avail_date:
            pts += 10
            reasons.append("Available now" if not listing.available_from else "Meets move-in date")

    # ── Freshness bonus (5 pts) ──────────────────────────────────────────
    from django.utils import timezone as _tz
    age_days = (_tz.now() - listing.created_at).days
    if age_days <= 3:
        pts += 5
        max_pts += 5
        reasons.append("Just listed" if age_days == 0 else f"Listed {age_days}d ago")

    # ── Bonus perks (up to 5 pts) ────────────────────────────────────────
    if 'no deposit' in tags_lower or 'no-deposit' in tags_lower:
        pts += 3
        max_pts += 3
        reasons.append("No deposit")
    if listing.featured:
        pts += 2
        max_pts += 2

    if max_pts == 0:
        return 70, reasons, tag_hits

    pct = int(round(pts / max_pts * 100))
    return min(100, max(0, pct)), reasons, tag_hits


def _fmm_explanation(listing, reasons, max_price_val, quality_tags,
                     accommodation_type='', property_type=''):
    """Generate a concrete, specific explanation of why a listing is a good fit."""
    from django.utils import timezone as _tz
    parts = []

    # Property/accommodation type match
    accom = listing.get_accommodation_type_display() if listing.accommodation_type else ''
    prop  = listing.get_property_type_display() if listing.property_type else ''
    if property_type and listing.property_type == property_type and prop:
        parts.append(f"it's exactly the {prop.lower()} you're looking for")
    elif accommodation_type and listing.accommodation_type == accommodation_type:
        label = 'whole place' if accommodation_type == 'whole' else 'private room'
        parts.append(f"it's a {label}{(' — ' + prop.lower()) if prop else ''}")

    # Budget insight — most important, be specific
    if listing.price and max_price_val:
        price = float(listing.price)
        budget = float(max_price_val)
        headroom = int(budget - price)
        pct_savings = int((headroom / budget) * 100) if budget else 0
        if listing.bills_included:
            effective = int(price - 150)
            parts.append(f"bills are included — effective cost is ~${effective:,}/mo, saving you ${int(budget - effective):,} vs your budget")
        elif headroom >= 500:
            parts.append(f"at ${int(price):,}/mo it's ${headroom:,} under your ${int(budget):,} budget — gives you room to save")
        elif headroom >= 100:
            parts.append(f"priced at ${int(price):,}/mo, ${headroom:,} under your budget")
        elif headroom >= 0:
            parts.append(f"right at your ${int(budget):,}/mo budget")

    # Tag/amenity matches — name them specifically
    matched = [t for t in quality_tags if t.lower() in listing.tags.lower()]
    if matched:
        if len(matched) >= 3:
            parts.append(f"it has all your must-haves: {', '.join(matched)}")
        elif len(matched) == 2:
            parts.append(f"it includes {matched[0]} and {matched[1]}")
        else:
            parts.append(f"it has {matched[0]}")

    # Extra perks from listing tags (even if not requested)
    tags_lower = listing.tags.lower() if listing.tags else ''
    perks = []
    if 'pet-friendly' in tags_lower and 'pet-friendly' not in [t.lower() for t in quality_tags]:
        perks.append('pet-friendly')
    if 'no deposit' in tags_lower or 'no-deposit' in tags_lower:
        perks.append('no deposit required')
    if 'furnished' in tags_lower and 'furnished' not in [t.lower() for t in quality_tags]:
        perks.append('fully furnished')
    if perks:
        parts.append(f"bonus: {', '.join(perks[:2])}")

    # Freshness
    age_days = (_tz.now() - listing.created_at).days
    if age_days == 0:
        parts.append("just listed today — move fast")
    elif age_days <= 3:
        parts.append(f"listed {age_days}d ago, still fresh")

    if not parts:
        # Fallback: generic but still specific to listing
        if listing.city:
            return f"Located in {listing.city} and within your search criteria."
        return None

    if len(parts) == 1:
        sentence = f"Good fit: {parts[0]}."
    elif len(parts) == 2:
        sentence = f"Good fit: {parts[0]}, and {parts[1]}."
    else:
        sentence = f"Good fit: {parts[0]}. Also — {', '.join(parts[1:])}."

    return sentence[0].upper() + sentence[1:]


def _render_db_setup_page(request):
    return render(request, 'db_not_ready.html', status=503)


def _listings_table_ready():
    try:
        return Listing._meta.db_table in connection.introspection.table_names()
    except OperationalError:
        return False


def listing_list(request):
    if not _listings_table_ready():
        return _render_db_setup_page(request)

    listings = Listing.objects.select_related('owner').prefetch_related('images').filter(
        status='active'
    ).filter(
        Q(expires_at__isnull=True) | Q(expires_at__gte=date.today())
    )

    q         = request.GET.get('q', '').strip()
    category  = request.GET.get('category', '').strip()
    city      = request.GET.get('city', '').strip().split(',')[0].strip()
    sort      = request.GET.get('sort', 'latest').strip()
    tag       = request.GET.get('tag', '').strip()
    min_price         = request.GET.get('min_price', '').strip()
    max_price         = request.GET.get('max_price', '').strip()
    tags_raw          = request.GET.get('tags', '').strip()
    available_by      = request.GET.get('available_by', '').strip()
    accommodation_type = request.GET.get('accommodation_type', '').strip()
    property_type      = request.GET.get('property_type', '').strip()
    bedrooms          = request.GET.get('bedrooms', '').strip()
    fmm               = request.GET.get('fmm', '').strip() == '1'

    # ── Text search ──
    terms = [t.strip() for t in q.split(',') if t.strip()] if q else []
    for term in terms:
        listings = listings.filter(
            Q(title__icontains=term) | Q(tags__icontains=term) | Q(description__icontains=term)
        )

    # ── Filters ──
    if category:
        listings = listings.filter(category=category)
    if city:
        listings = listings.filter(city__icontains=city)
    if tag:
        listings = listings.filter(tags__icontains=tag)
    if accommodation_type:
        listings = listings.filter(accommodation_type=accommodation_type)
    if property_type:
        listings = listings.filter(property_type=property_type)
    if bedrooms:
        try:
            listings = listings.filter(bedrooms=int(bedrooms))
        except ValueError:
            pass

    # Quality tags (multi-select from chips)
    quality_tags = [t.strip() for t in tags_raw.split(',') if t.strip()]
    if quality_tags and not fmm:
        # Regular mode only: hard-filter AND — listing must have ALL selected tags
        for qt in quality_tags:
            listings = listings.filter(tags__icontains=qt)
    # FMM mode: tags are soft preferences — scoring handles them, no hard filter

    # Price range
    try:
        if min_price:
            listings = listings.filter(price__gte=float(min_price))
        if max_price:
            listings = listings.filter(price__lte=float(max_price))
    except ValueError:
        pass

    # Availability — show listings available on or before the requested date
    # (listings with no available_from are treated as available now)
    if available_by:
        from datetime import date as _date
        try:
            _avail = _date.fromisoformat(available_by)
            listings = listings.filter(
                Q(available_from__isnull=True) | Q(available_from__lte=_avail)
            )
        except ValueError:
            pass

    # ── Relevance scoring (title match > tag match > description only) ──
    if terms:
        score_cases = []
        for term in terms:
            score_cases.append(When(title__icontains=term, then=Value(3)))
            score_cases.append(When(tags__icontains=term, then=Value(2)))
            score_cases.append(When(description__icontains=term, then=Value(1)))
        listings = listings.annotate(
            relevance=Case(*score_cases, default=Value(0), output_field=IntegerField())
        )

    # ── Ordering ──
    if fmm:
        # FMM: sort by match score (computed below); fall back to featured then date
        listings = listings.order_by('-featured', '-created_at')
    elif sort == 'price_low':
        listings = listings.order_by('price', '-featured', '-created_at')
    elif sort == 'price_high':
        listings = listings.order_by('-price', '-featured', '-created_at')
    elif sort == 'best_match' and terms:
        listings = listings.order_by('-relevance', '-featured', '-created_at')
    else:
        listings = listings.order_by('-featured', '-created_at')

    # Auto-switch to best_match when user is searching and hasn't chosen another sort
    if terms and sort == 'latest' and not fmm:
        listings = listings.order_by('-relevance', '-featured', '-created_at')
        sort = 'best_match'

    # ── FMM scoring ──
    listing_scores = {}
    listing_score_classes = {}
    listing_reasons = {}
    listing_explanations = {}
    fmm_inputs = None
    fmm_market = None
    near_match_listings = []

    if fmm:
        max_price_val = None
        if max_price:
            try:
                max_price_val = float(max_price)
            except ValueError:
                pass

        avail_date = None
        if available_by:
            from datetime import date as _date
            try:
                avail_date = _date.fromisoformat(available_by)
            except ValueError:
                pass

        # ── Score ALL listings in the filtered set ──
        scored = []
        for l in list(listings):
            pct, reasons, tag_hits = _fmm_score(
                l, max_price_val, quality_tags, avail_date,
                accommodation_type=accommodation_type,
                property_type=property_type,
            )
            scored.append((l, pct, reasons, tag_hits))
        scored.sort(key=lambda x: (-x[1], -x[0].featured, x[0].created_at))

        # ── Split into exact matches (≥50%) vs near matches (<50%) ──
        # Lower threshold so partial matches (missing tags) still surface
        exact_scored  = [x for x in scored if x[1] >= 50]
        near_scored   = [x for x in scored if x[1] < 50]

        # If nothing hits 50%, show everything as near matches so user is never left with 0
        if not exact_scored and not near_scored:
            near_scored = scored
        elif not exact_scored:
            # Promote top near matches to exact so the page isn't empty
            exact_scored  = near_scored[:6]
            near_scored   = near_scored[6:]

        listings             = [x[0] for x in exact_scored]
        near_match_listings  = [x[0] for x in near_scored[:4]]  # show up to 4

        listing_scores        = {x[0].pk: x[1] for x in scored}
        listing_score_classes = {x[0].pk: 'high' if x[1] >= 85 else 'mid' for x in scored}
        listing_reasons       = {x[0].pk: x[2] for x in scored}
        listing_explanations  = {
            x[0].pk: _fmm_explanation(
                x[0], x[2], max_price_val, quality_tags,
                accommodation_type=accommodation_type,
                property_type=property_type,
            )
            for x in scored
        }

        # ── Market context ──
        total_in_city = Listing.objects.filter(city__icontains=city).count() if city else 0
        prices_in_city = list(
            Listing.objects.filter(city__icontains=city, price__isnull=False)
            .values_list('price', flat=True)
        ) if city else []
        median_price = None
        if prices_in_city:
            s = sorted(prices_in_city)
            mid = len(s) // 2
            median_price = int(s[mid] if len(s) % 2 else (s[mid - 1] + s[mid]) / 2)

        budget_realistic = None
        if max_price_val and median_price:
            ratio = float(max_price_val) / median_price
            if ratio >= 1.1:
                budget_realistic = 'above'
            elif ratio >= 0.9:
                budget_realistic = 'at'
            else:
                budget_realistic = 'below'

        category_label = dict(Listing.CATEGORY_CHOICES).get(category, '')
        avail_display = ''
        if available_by:
            from datetime import date as _date2
            try:
                avail_display = _date2.fromisoformat(available_by).strftime('%b %-d')
            except ValueError:
                avail_display = available_by

        accom_label = dict(Listing.ACCOMMODATION_TYPE_CHOICES).get(accommodation_type, '')
        prop_label  = dict(Listing.PROPERTY_TYPE_CHOICES).get(property_type, '')

        fmm_inputs = {
            'city': city,
            'max_price': max_price,
            'category': category,
            'category_label': category_label,
            'accommodation_type': accommodation_type,
            'accommodation_label': accom_label,
            'property_type': property_type,
            'property_label': prop_label,
            'tags': quality_tags,
            'available_by': avail_display,
        }
        fmm_market = {
            'total_in_city': total_in_city,
            'exact_count': len(exact_scored),
            'near_count': len(near_scored),
            'median_price': median_price,
            'budget_realistic': budget_realistic,
        }

    category_counts = dict(
        Listing.objects.values_list('category').annotate(total=Count('id'))
    )

    fav_ids = set()
    if request.user.is_authenticated:
        fav_ids = set(Favourite.objects.filter(user=request.user).values_list('listing_id', flat=True))

    context = {
        'listings': list(listings),
        'fav_ids': fav_ids,
        'category_choices': Listing.CATEGORY_CHOICES,
        'wizard_categories': [c for c in Listing.CATEGORY_CHOICES if c[0] in ('rentals', 'properties')],
        'category_counts': category_counts,
        'total_listings': Listing.objects.count(),
        'featured_count': Listing.objects.filter(featured=True).count(),
        'filters': {
            'q': q, 'category': category, 'city': city, 'sort': sort, 'tag': tag,
            'min_price': min_price, 'max_price': max_price, 'tags': tags_raw,
            'available_by': available_by,
        },
        'active_quality_tags': quality_tags,
        'new_threshold': timezone.now() - timedelta(hours=48),
        'fmm_mode': fmm,
        'fmm_inputs': fmm_inputs,
        'fmm_market': fmm_market,
        'near_match_listings': near_match_listings,
        'listing_scores': listing_scores,
        'listing_score_classes': listing_score_classes,
        'listing_reasons': listing_reasons,
        'listing_explanations': listing_explanations,
    }

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return render(request, 'listings/_listings_grid.html', context)

    return render(request, 'listings/listing_list.html', context)


def guided_search(request):
    if request.method == 'POST':
        GuidedSearchEvent.objects.create(event_type=GuidedSearchEvent.COMPLETE)
    else:
        GuidedSearchEvent.objects.create(event_type=GuidedSearchEvent.START)
    mode = request.GET.get('mode', '').strip()  # 'rent' | 'buy' | ''
    return render(request, 'listings/guided_search.html', {
        'category_choices': Listing.CATEGORY_CHOICES,
        'gs_mode': mode,
    })


def listing_detail(request, pk):
    if not _listings_table_ready():
        return _render_db_setup_page(request)

    listing = get_object_or_404(Listing.objects.select_related('owner').prefetch_related('images'), pk=pk)

    # Increment view count (skip owner's own visits)
    if not request.user.is_authenticated or request.user != listing.owner:
        Listing.objects.filter(pk=pk).update(view_count=django_models.F('view_count') + 1)
        listing.view_count += 1

    if request.method == 'POST':
        inquiry_form = ListingInquiryForm(request.POST)
        if inquiry_form.is_valid():
            inquiry = inquiry_form.save(commit=False)
            inquiry.listing = listing
            inquiry.save()
            if listing.owner.email:
                send_mail(
                    subject=f'New inquiry for "{listing.title}"',
                    message=(
                        f'Hi {listing.owner.username},\n\n'
                        f'{inquiry.name} sent an inquiry about your listing "{listing.title}".\n\n'
                        f'Message:\n{inquiry.message}\n\n'
                        f'Reply to: {inquiry.email}'
                        + (f'\nPhone: {inquiry.phone}' if inquiry.phone else '')
                    ),
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[listing.owner.email],
                    fail_silently=True,
                )
            # Create a lead record for the agent portal
            lead = Lead.objects.create(
                name=inquiry.name,
                email=inquiry.email,
                phone=inquiry.phone or '',
                source='inquiry',
                listing=listing,
            )
            LeadPreference.objects.create(
                lead=lead,
                city=listing.city,
                property_type=listing.category,
            )
            messages.success(request, 'Your inquiry was sent to the lister.')
            return redirect('listing_detail', pk=listing.pk)
    else:
        inquiry_form = ListingInquiryForm()

    return render(
        request,
        'listings/listing_detail.html',
        {'listing': listing, 'inquiry_form': inquiry_form},
    )


@login_required
def edit_listing(request, pk):
    if not _listings_table_ready():
        return _render_db_setup_page(request)

    listing = get_object_or_404(Listing, pk=pk, owner=request.user)

    if request.method == 'POST':
        form = ListingForm(request.POST, instance=listing)
        new_files = request.FILES.getlist('images')

        # Process deletions first so count is accurate
        delete_ids = [int(x) for x in request.POST.getlist('delete_images') if x.isdigit()]
        existing_count = listing.images.count() - len(delete_ids)

        image_errors = validate_uploaded_images(new_files, existing_count=max(existing_count, 0))

        if form.is_valid() and not image_errors:
            form.save()
            # Delete selected images
            if delete_ids:
                listing.images.filter(pk__in=delete_ids).delete()
            # Save new images
            next_order = listing.images.count()
            for i, f in enumerate(new_files):
                ListingImage.objects.create(listing=listing, image=f, order=next_order + i)
            messages.success(request, 'Listing updated successfully.')
            return redirect('listing_detail', pk=listing.pk)
    else:
        form = ListingForm(instance=listing)
        image_errors = []

    return render(request, 'listings/edit_listing.html', {
        'form': form,
        'listing': listing,
        'existing_images': listing.images.all(),
        'image_errors': image_errors,
        'max_images': 8,
    })


@login_required
def toggle_favourite(request, pk):
    if request.method == 'POST':
        listing = get_object_or_404(Listing, pk=pk)
        fav, created = Favourite.objects.get_or_create(user=request.user, listing=listing)
        if not created:
            fav.delete()
            is_fav = False
        else:
            is_fav = True
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'is_favourite': is_fav})
    return redirect(request.POST.get('next', 'listing_list'))


@login_required
def saved_listings(request):
    favourites = (
        Favourite.objects
        .filter(user=request.user)
        .select_related('listing', 'listing__owner')
        .prefetch_related('listing__images')
        .order_by('-created_at')
    )
    listings = [f.listing for f in favourites]
    fav_ids = {l.pk for l in listings}
    return render(request, 'listings/saved_listings.html', {
        'listings': listings,
        'fav_ids': fav_ids,
    })


@login_required
def create_listing(request):
    if not _listings_table_ready():
        return _render_db_setup_page(request)

    if request.method == 'POST':
        form = ListingForm(request.POST)
        new_files = request.FILES.getlist('images')
        image_errors = validate_uploaded_images(new_files)

        # ── City launch gate ──────────────────────────────────────────
        if settings.LAUNCH_ACTIVE:
            submitted_city = request.POST.get('city', '').strip().lower()
            if submitted_city and submitted_city not in settings.LAUNCH_CITIES:
                return render(request, 'listings/coming_soon.html', {
                    'city': request.POST.get('city', '').strip().title(),
                })

        if form.is_valid() and not image_errors:
            listing = form.save(commit=False)
            listing.owner = request.user
            listing.save()
            for i, f in enumerate(new_files):
                ListingImage.objects.create(listing=listing, image=f, order=i)
            return redirect('listing_detail', pk=listing.pk)
    else:
        form = ListingForm()
        image_errors = []

    return render(request, 'listings/create_listing.html', {
        'form': form,
        'image_errors': image_errors,
        'max_images': 8,
    })


def waitlist_signup(request):
    """Handle city waitlist form submission."""
    if request.method == 'POST':
        email = request.POST.get('email', '').strip()
        city  = request.POST.get('city', '').strip()
        state = request.POST.get('state', '').strip()
        if email and city:
            CityWaitlist.objects.get_or_create(
                email=email,
                city=city.lower(),
                defaults={'state': state},
            )
        return render(request, 'listings/coming_soon.html', {
            'city':    city.title(),
            'joined':  True,
            'email':   email,
        })
    return redirect('listing_list')


@login_required
def delete_listing(request, pk):
    listing = get_object_or_404(Listing, pk=pk, owner=request.user)
    if request.method == 'POST':
        listing.delete()
        return redirect('profile')
    return render(request, 'listings/confirm_delete.html', {'listing': listing})


@login_required
def listing_inquiries(request, pk):
    listing = get_object_or_404(Listing, pk=pk, owner=request.user)
    inquiries = listing.inquiries.order_by('-created_at')
    return render(request, 'listings/listing_inquiries.html', {
        'listing':   listing,
        'inquiries': inquiries,
    })
