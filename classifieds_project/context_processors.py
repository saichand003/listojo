import os


def ui_asset_version(request):
    return {
        'UI_ASSET_VERSION': os.getenv('UI_ASSET_VERSION', '2026-04-10-1'),
    }
