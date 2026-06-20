from datetime import timedelta

from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Sum
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import redirect, render

from accounts.services.dashboard import owner_inquiries, owner_listing_overview, owner_performance, staff_agent_dashboard
from .forms import RegistrationForm

REMEMBER_ME_AGE = 60 * 60 * 24 * 90  # 90 days


def user_login(request):
    if request.user.is_authenticated:
        return redirect('listing_list')

    error = None
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        remember = request.POST.get('remember_me') == 'on'

        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            request.session.set_expiry(REMEMBER_ME_AGE if remember else 0)
            return redirect(request.POST.get('next') or request.GET.get('next') or 'listing_list')
        error = 'Invalid username or password.'

    return render(request, 'registration/login.html', {
        'error': error,
        'next': request.GET.get('next', ''),
    })


def user_logout(request):
    logout(request)
    return redirect('listing_list')
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
    profile_obj, _ = request.user.profile.__class__.objects.get_or_create(user=request.user)
    return render(request, 'accounts/profile.html', {'profile': profile_obj})


def _normalize_phone(raw: str) -> str:
    """Best-effort US E.164 normalisation. Returns '' if it can't be salvaged."""
    raw = (raw or '').strip()
    if raw.startswith('+'):
        digits = '+' + ''.join(c for c in raw[1:] if c.isdigit())
        return digits if len(digits) >= 11 else ''
    digits = ''.join(c for c in raw if c.isdigit())
    if len(digits) == 10:
        return '+1' + digits
    if len(digits) == 11 and digits.startswith('1'):
        return '+' + digits
    return ''


@login_required
def send_phone_code(request):
    """Save the phone (unverified) and send a Twilio Verify OTP."""
    if request.method != 'POST':
        return JsonResponse({'ok': False, 'error': 'method not allowed'}, status=405)

    from accounts.models import UserProfile
    from accounts.services.twilio_service import start_verification

    phone = _normalize_phone(request.POST.get('phone', ''))
    if not phone:
        return JsonResponse({'ok': False, 'error': 'Enter a valid US phone number.'}, status=400)

    profile_obj, _ = UserProfile.objects.get_or_create(user=request.user)
    # New/changed number resets verification
    if profile_obj.phone != phone:
        profile_obj.phone = phone
        profile_obj.phone_verified = False
    profile_obj.save(update_fields=['phone', 'phone_verified'])

    sent = start_verification(phone)
    if not sent:
        return JsonResponse({
            'ok': False,
            'error': 'Could not send code right now. SMS may not be configured yet.',
            'phone': phone,
        }, status=200)
    return JsonResponse({'ok': True, 'phone': phone})


@login_required
def verify_phone_code(request):
    """Check the OTP; on success mark verified and opt into SMS alerts."""
    if request.method != 'POST':
        return JsonResponse({'ok': False, 'error': 'method not allowed'}, status=405)

    from accounts.models import UserProfile
    from accounts.services.twilio_service import check_verification

    code = (request.POST.get('code', '') or '').strip()
    profile_obj, _ = UserProfile.objects.get_or_create(user=request.user)
    if not profile_obj.phone or not code:
        return JsonResponse({'ok': False, 'error': 'Missing phone or code.'}, status=400)

    if check_verification(profile_obj.phone, code):
        profile_obj.phone_verified = True
        profile_obj.notify_sms = True   # auto opt-in on successful verify
        profile_obj.save(update_fields=['phone_verified', 'notify_sms'])
        return JsonResponse({'ok': True, 'verified': True})
    return JsonResponse({'ok': False, 'error': 'Invalid or expired code.'}, status=200)


@login_required
def update_notification_prefs(request):
    """Toggle email/SMS notification preferences."""
    if request.method != 'POST':
        return JsonResponse({'ok': False, 'error': 'method not allowed'}, status=405)

    from accounts.models import UserProfile
    profile_obj, _ = UserProfile.objects.get_or_create(user=request.user)
    profile_obj.notify_email = request.POST.get('notify_email') == 'true'
    want_sms = request.POST.get('notify_sms') == 'true'
    # SMS can only be enabled with a verified phone
    profile_obj.notify_sms = want_sms and profile_obj.phone_verified
    profile_obj.save(update_fields=['notify_email', 'notify_sms'])
    return JsonResponse({
        'ok': True,
        'notify_email': profile_obj.notify_email,
        'notify_sms': profile_obj.notify_sms,
    })


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
