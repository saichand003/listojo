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
            from accounts.services import login_otp
            next_url = request.POST.get('next') or request.GET.get('next') or ''
            # Trusted device → skip OTP and log in directly.
            if login_otp.is_trusted_device(request, user):
                login(request, user, backend='django.contrib.auth.backends.ModelBackend')
                request.session.set_expiry(REMEMBER_ME_AGE if remember else 0)
                return redirect(next_url or 'listing_list')
            # Otherwise step-up: confirm via OTP before the session starts.
            login_otp.begin(request, user, remember=remember, next_url=next_url)
            login_otp.start_email_otp(request, user, force=True)
            return redirect('login_confirm')
        error = 'Invalid username or password.'

    return render(request, 'registration/login.html', {
        'error': error,
        'next': request.GET.get('next', ''),
    })


def login_confirm(request):
    """'Confirm it's you' — verify the OTP, then complete the login."""
    from django.contrib.auth.models import User
    from accounts.services import login_otp

    uid = login_otp.pending_user_id(request)
    if not uid:
        return redirect('login')
    try:
        user = User.objects.select_related('profile').get(pk=uid)
    except User.DoesNotExist:
        login_otp.clear(request)
        return redirect('login')

    error = None
    if request.method == 'POST':
        code = request.POST.get('code', '')
        if login_otp.check_otp(request, user, code):
            remember, next_url = login_otp.pop_intent(request)
            trust = request.POST.get('trust_device') == 'on'
            login_otp.clear(request)
            # Explicit backend required — allauth adds a second auth backend.
            login(request, user, backend='django.contrib.auth.backends.ModelBackend')
            request.session.set_expiry(REMEMBER_ME_AGE if remember else 0)
            resp = redirect(next_url or 'listing_list')
            if trust:
                login_otp.set_trusted_cookie(resp, user)
            return resp
        error = 'Invalid or expired code. Try again.'

    profile = getattr(user, 'profile', None)
    has_phone = bool(profile and profile.phone_verified and profile.phone)
    ch = login_otp.channel(request)
    return render(request, 'registration/login_confirm.html', {
        'error': error,
        'channel': ch,
        'sent_to': login_otp.mask_phone(profile.phone) if ch == 'sms' and profile else login_otp.mask_email(user.email),
        'has_phone': has_phone,
        'phone_masked': login_otp.mask_phone(profile.phone) if has_phone else '',
    })


def login_confirm_resend(request):
    """Resend the code on the current channel."""
    from django.contrib.auth.models import User
    from accounts.services import login_otp
    uid = login_otp.pending_user_id(request)
    if not uid:
        return JsonResponse({'ok': False}, status=400)
    user = User.objects.select_related('profile').get(pk=uid)
    if login_otp.channel(request) == 'sms':
        ok = login_otp.start_sms_otp(request, user)
    else:
        ok = login_otp.start_email_otp(request, user)
    return JsonResponse({'ok': ok})


def login_confirm_switch(request):
    """'Try another way' — switch the code channel (email ⇄ sms)."""
    from django.contrib.auth.models import User
    from accounts.services import login_otp
    uid = login_otp.pending_user_id(request)
    if not uid:
        return JsonResponse({'ok': False}, status=400)
    user = User.objects.select_related('profile').get(pk=uid)
    to = request.POST.get('channel', 'sms')
    if to == 'sms':
        ok = login_otp.start_sms_otp(request, user)
    else:
        ok = login_otp.start_email_otp(request, user)
    return JsonResponse({'ok': ok})


def user_logout(request):
    logout(request)
    return redirect('listing_list')
from listings.models import ListingInquiry


def register(request):
    from accounts.services import security, signup_otp
    error = None
    if request.method == 'POST':
        # Bot / abuse controls before doing any work.
        if not security.rate_limit(request, key='signup', limit=5, window=3600):
            return render(request, 'accounts/register.html',
                          {'form': RegistrationForm(), 'error': 'Too many attempts. Please try again later.'})
        if not security.verify_turnstile(request):
            return render(request, 'accounts/register.html',
                          {'form': RegistrationForm(), 'error': 'Bot check failed. Please try again.'})

        form = RegistrationForm(request.POST)
        if form.is_valid():
            # Don't create the account yet — verify the email first.
            signup_otp.begin(
                request,
                username=form.cleaned_data['username'],
                email=form.cleaned_data['email'],
                password=form.cleaned_data['password1'],
            )
            return redirect('register_confirm')
    else:
        form = RegistrationForm()
    return render(request, 'accounts/register.html', {'form': form, 'error': error})


def register_confirm(request):
    """Verify the emailed code, then actually create the account and log in."""
    from accounts.services import signup_otp
    data = signup_otp.pending(request)
    if not data:
        return redirect('register')

    error = None
    if request.method == 'POST':
        if signup_otp.check(request, request.POST.get('code', '')):
            user = signup_otp.complete(request)
            if user:
                login(request, user, backend='django.contrib.auth.backends.ModelBackend')
                return redirect('listing_list')
            error = 'That username or email was just taken. Please start over.'
        else:
            error = 'Invalid or expired code. Try again.'

    return render(request, 'accounts/register_confirm.html', {
        'error': error,
        'sent_to': _mask_email(data['email']),
    })


def register_confirm_resend(request):
    from accounts.services import security, signup_otp
    if not security.rate_limit(request, key='signup_resend', limit=5, window=600):
        return JsonResponse({'ok': False, 'error': 'Too many requests'}, status=429)
    return JsonResponse({'ok': signup_otp.resend(request)})


def _mask_email(email: str) -> str:
    from accounts.services.login_otp import mask_email
    return mask_email(email)


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
