import os
from django.conf import settings


def ui_asset_version(request):
    return {
        'UI_ASSET_VERSION': os.getenv('UI_ASSET_VERSION', '2026-04-17-02'),
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
