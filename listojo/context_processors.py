import os
from django.conf import settings
from django.urls import translate_url
from django.utils.translation import get_language


def ui_asset_version(request):
    return {
        'UI_ASSET_VERSION': os.getenv('UI_ASSET_VERSION', '2026-10-08-es-light'),
    }


def sidebar_counts(request):
    if not request.user.is_authenticated:
        return {}
    try:
        from listings.models import ListingInquiry
        inquiry_count = ListingInquiry.objects.filter(
            listing__owner=request.user,
            is_read=False,
        ).count()
    except Exception:
        inquiry_count = 0
    try:
        from chatapp.models import ChatMessage
        unread_message_count = ChatMessage.objects.filter(
            recipient=request.user,
            is_read=False,
        ).count()
    except Exception:
        unread_message_count = 0
    return {
        'sb_inquiry_count': inquiry_count,
        'sb_unread_message_count': unread_message_count,
    }


def launch_config(request):
    return {
        'launch_active':  settings.LAUNCH_ACTIVE,
        'launch_regions': settings.LAUNCH_REGIONS,
    }


def google_maps(request):
    return {
        'GOOGLE_MAPS_API_KEY': settings.GOOGLE_MAPS_API_KEY,
    }


def feature_flags(request):
    """Expose whether phone verification is live (Twilio Verify configured)."""
    verify_enabled = bool(
        getattr(settings, 'TWILIO_ACCOUNT_SID', '')
        and getattr(settings, 'TWILIO_AUTH_TOKEN', '')
        and getattr(settings, 'TWILIO_VERIFY_SERVICE_SID', '')
    )
    google_login_enabled = bool(
        getattr(settings, 'GOOGLE_OAUTH_CLIENT_ID', '')
        and getattr(settings, 'GOOGLE_OAUTH_CLIENT_SECRET', '')
    )
    return {
        'PHONE_VERIFY_ENABLED': verify_enabled,
        'GOOGLE_LOGIN_ENABLED': google_login_enabled,
        'TURNSTILE_SITE_KEY': getattr(settings, 'TURNSTILE_SITE_KEY', ''),
        'TURNSTILE_ENABLED': bool(getattr(settings, 'TURNSTILE_SITE_KEY', '') and getattr(settings, 'TURNSTILE_SECRET_KEY', '')),
    }


def language_switch(request):
    """
    The EN | ES links in the nav: the current page in the other language.

    Only pages that exist in both languages get the switch. Elsewhere
    translate_url hands back the same URL, and a toggle that does nothing
    is worse than no toggle.
    """
    current = get_language() or settings.LANGUAGE_CODE
    path = request.get_full_path()
    links = []
    for code, label in settings.LANGUAGES:
        url = path if code == current else translate_url(path, code)
        if code != current and url == path:
            return {}
        links.append({'code': code, 'label': code.upper(), 'name': label, 'url': url, 'active': code == current})
    return {'language_links': links, 'LANGUAGE_CODE': current}
