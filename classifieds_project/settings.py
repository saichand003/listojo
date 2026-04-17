import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / '.env')

SECRET_KEY = os.getenv('DJANGO_SECRET_KEY', 'dev-only-secret-key-change-me')
DEBUG = os.getenv('DJANGO_DEBUG', 'true').lower() == 'true'
ALLOWED_HOSTS = [h.strip() for h in os.getenv('DJANGO_ALLOWED_HOSTS', '127.0.0.1,localhost,192.168.1.33').split(',') if h.strip()]
CSRF_TRUSTED_ORIGINS = [o.strip() for o in os.getenv('DJANGO_CSRF_TRUSTED_ORIGINS', '').split(',') if o.strip()]

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'accounts',
    'listings',
    'chatapp',
    'portal',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'classifieds_project.middleware.DatabaseNotReadyMiddleware',
]

ROOT_URLCONF = 'classifieds_project.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'classifieds_project.context_processors.ui_asset_version',
                'classifieds_project.context_processors.launch_config',
                'classifieds_project.context_processors.google_maps',
            ],
        },
    },
]

WSGI_APPLICATION = 'classifieds_project.wsgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
MEDIA_URL = 'media/'
MEDIA_ROOT = BASE_DIR / 'media'

LOGIN_URL = 'login'
LOGIN_REDIRECT_URL = 'listing_list'
LOGOUT_REDIRECT_URL = 'listing_list'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ── Google Maps ──────────────────────────────────────────────────────────────
GOOGLE_MAPS_API_KEY = os.getenv('GOOGLE_MAPS_API_KEY', '')

# ── City rollout ─────────────────────────────────────────────────────────────
# Set LAUNCH_ACTIVE = False to open the platform to all cities.
# To add a new metro, append a block to LAUNCH_REGIONS and re-derive LAUNCH_CITIES.
LAUNCH_ACTIVE = os.getenv('LAUNCH_ACTIVE', 'true').lower() == 'true'

LAUNCH_REGIONS = {
    'dallas-fortworth': {
        'label': 'Dallas–Fort Worth Metroplex',
        'state': 'TX',
        'cities': {
            'dallas', 'fort worth', 'arlington', 'plano', 'irving',
            'garland', 'frisco', 'mckinney', 'grand prairie', 'mesquite',
            'carrollton', 'denton', 'richardson', 'lewisville', 'allen',
            'flower mound', 'north richland hills', 'wylie', 'mansfield',
            'euless', 'cedar hill', 'hurst', 'grapevine', 'rowlett',
            'coppell', 'keller', 'rockwall', 'southlake', 'colleyville',
            'duncanville', 'desoto', 'bedford', 'the colony', 'burleson',
            'haltom city', 'waxahachie', 'cleburne', 'weatherford',
            'forney', 'sachse', 'murphy', 'fate', 'anna', 'prosper',
            'celina', 'little elm', 'oak cliff',
        },
    },
    # Phase 2 — uncomment to expand:
    # 'houston': {
    #     'label': 'Greater Houston',
    #     'state': 'TX',
    #     'cities': {'houston', 'sugar land', 'pearland', 'pasadena',
    #                'katy', 'baytown', 'conroe', 'league city', 'humble'},
    # },
    # 'austin': {
    #     'label': 'Austin Metro',
    #     'state': 'TX',
    #     'cities': {'austin', 'round rock', 'cedar park', 'pflugerville',
    #                'georgetown', 'kyle', 'buda', 'san marcos'},
    # },
}

# Flat lowercase set used for O(1) city lookups
LAUNCH_CITIES = {
    city.lower()
    for region in LAUNCH_REGIONS.values()
    for city in region['cities']
}

# Security hardening: enabled when DEBUG is False (production mode).
if not DEBUG:
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SECURE_REFERRER_POLICY = 'same-origin'
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = 'DENY'
    SESSION_COOKIE_HTTPONLY = True
    CSRF_COOKIE_HTTPONLY = True
    SESSION_COOKIE_AGE = 60 * 60 * 24
