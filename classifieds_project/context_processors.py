import os
from django.conf import settings


def ui_asset_version(request):
    return {
        'UI_ASSET_VERSION': os.getenv('UI_ASSET_VERSION', '2026-04-21-01'),
    }


def sidebar_counts(request):
    if not request.user.is_authenticated:
        return {}
    try:
        from listings.models import ListingInquiry
        inquiry_count = ListingInquiry.objects.filter(
            listing__owner=request.user,
        ).count()
    except Exception:
        inquiry_count = 0
    return {'sb_inquiry_count': inquiry_count}


def launch_config(request):
    return {
        'launch_active':  settings.LAUNCH_ACTIVE,
        'launch_regions': settings.LAUNCH_REGIONS,
    }


def google_maps(request):
    return {
        'GOOGLE_MAPS_API_KEY': settings.GOOGLE_MAPS_API_KEY,
    }
