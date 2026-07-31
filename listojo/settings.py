import os
import dj_database_url
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
    'django.contrib.humanize',
    # Social login (Google) via django-allauth
    'django.contrib.sites',
    'allauth',
    'allauth.account',
    'allauth.socialaccount',
    'allauth.socialaccount.providers.google',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'allauth.account.middleware.AccountMiddleware',
    'listojo.middleware.SubdomainPortalMiddleware',
    'listojo.middleware.DatabaseNotReadyMiddleware',
]

ROOT_URLCONF = 'listojo.urls'

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
                'listojo.context_processors.ui_asset_version',
                'listojo.context_processors.launch_config',
                'listojo.context_processors.google_maps',
                'listojo.context_processors.feature_flags',
                'listojo.context_processors.sidebar_counts',
            ],
        },
    },
]

WSGI_APPLICATION = 'listojo.wsgi.application'

_DATABASE_URL = os.getenv('DATABASE_URL')
if _DATABASE_URL:
    DATABASES = {'default': dj_database_url.config(default=_DATABASE_URL, conn_max_age=600, ssl_require=True)}
else:
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
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static']

# ── Media / File Storage ──────────────────────────────────────────────────────
# In production, upload media to Cloudflare R2 (S3-compatible, no egress fees).
# Set R2_* env vars in Railway to activate. Falls back to local media/ in dev.
_R2_BUCKET = os.getenv('R2_BUCKET_NAME', '')
if _R2_BUCKET:
    AWS_STORAGE_BUCKET_NAME = _R2_BUCKET
    AWS_ACCESS_KEY_ID       = os.getenv('R2_ACCESS_KEY_ID', '')
    AWS_SECRET_ACCESS_KEY   = os.getenv('R2_SECRET_ACCESS_KEY', '')
    AWS_S3_ENDPOINT_URL     = os.getenv('R2_ENDPOINT_URL', '')
    AWS_S3_CUSTOM_DOMAIN    = os.getenv('R2_PUBLIC_DOMAIN', '')
    AWS_DEFAULT_ACL         = None
    AWS_S3_FILE_OVERWRITE   = False
    AWS_QUERYSTRING_AUTH    = False
    MEDIA_URL = f'https://{AWS_S3_CUSTOM_DOMAIN}/'
    STORAGES = {
        'default': {
            'BACKEND': 'storages.backends.s3boto3.S3Boto3Storage',
        },
        'staticfiles': {
            'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage',
        },
    }
else:
    MEDIA_URL  = 'media/'
    MEDIA_ROOT = BASE_DIR / 'media'
    STORAGES = {
        'default': {
            'BACKEND': 'django.core.files.storage.FileSystemStorage',
        },
        'staticfiles': {
            'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage',
        },
    }

LOGIN_URL = 'login'
LOGIN_REDIRECT_URL = 'listing_list'
LOGOUT_REDIRECT_URL = 'listing_list'

# ── Social login (django-allauth / Google) ───────────────────────────────────
SITE_ID = 1
AUTHENTICATION_BACKENDS = [
    'django.contrib.auth.backends.ModelBackend',           # username/password (existing)
    'allauth.account.auth_backends.AuthenticationBackend',  # social login
]

GOOGLE_OAUTH_CLIENT_ID     = os.getenv('GOOGLE_OAUTH_CLIENT_ID', '')
GOOGLE_OAUTH_CLIENT_SECRET = os.getenv('GOOGLE_OAUTH_CLIENT_SECRET', '')

# Google emails are already verified — frictionless: no extra signup form,
# no verification email, straight through to Google on click.
ACCOUNT_EMAIL_VERIFICATION = 'none'
SOCIALACCOUNT_AUTO_SIGNUP  = True
SOCIALACCOUNT_LOGIN_ON_GET = True
SOCIALACCOUNT_ADAPTER      = 'accounts.adapters.SocialAccountAdapter'

SOCIALACCOUNT_PROVIDERS = {
    'google': {
        'APPS': [{
            'client_id': GOOGLE_OAUTH_CLIENT_ID,
            'secret':    GOOGLE_OAUTH_CLIENT_SECRET,
            'key': '',
        }],
        'SCOPE': ['profile', 'email'],
        'AUTH_PARAMS': {'access_type': 'online'},
        'OAUTH_PKCE_ENABLED': True,
    },
}

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ── Email ─────────────────────────────────────────────────────────────────────
# In development, emails are printed to the console.
# In production, set EMAIL_BACKEND to 'django.core.mail.backends.smtp.EmailBackend'
# and configure EMAIL_HOST, EMAIL_PORT, EMAIL_HOST_USER, EMAIL_HOST_PASSWORD via .env
EMAIL_BACKEND  = os.getenv('EMAIL_BACKEND', 'django.core.mail.backends.console.EmailBackend')
EMAIL_HOST     = os.getenv('EMAIL_HOST', 'smtp.gmail.com')
EMAIL_PORT     = int(os.getenv('EMAIL_PORT', '587'))
EMAIL_USE_TLS  = os.getenv('EMAIL_USE_TLS', 'true').lower() == 'true'
EMAIL_HOST_USER     = os.getenv('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.getenv('EMAIL_HOST_PASSWORD', '')
DEFAULT_FROM_EMAIL  = os.getenv('DEFAULT_FROM_EMAIL', 'Listojo <noreply@listojo.com>')
# Fail fast on a slow/unreachable SMTP server instead of hanging the request.
EMAIL_TIMEOUT = int(os.getenv('EMAIL_TIMEOUT', '10'))
# Resend HTTP-API backend (bypasses blocked SMTP ports on cloud hosts).
# Set EMAIL_BACKEND=listojo.email_backends.ResendEmailBackend to use it.
RESEND_API_KEY = os.getenv('RESEND_API_KEY', '') or EMAIL_HOST_PASSWORD

# ── Google Maps ──────────────────────────────────────────────────────────────
# Browser key — used in templates for the JS Maps API. Restrict by HTTP referrer.
GOOGLE_MAPS_API_KEY = os.getenv('GOOGLE_MAPS_API_KEY', '')
# Server-side key — used for the Geocoding API (no referrer). Restrict by IP / API.
# Falls back to the browser key if not separately configured.
GOOGLE_GEOCODING_API_KEY = os.getenv('GOOGLE_GEOCODING_API_KEY', '') or GOOGLE_MAPS_API_KEY

# ── Walk Score ───────────────────────────────────────────────────────────────
# Server-side key from walkscore.com/professional/api. Absent key = feature is
# simply skipped; scores stay null and the UI section hides itself.
WALKSCORE_API_KEY = os.getenv('WALKSCORE_API_KEY', '')

# ── Site ──────────────────────────────────────────────────────────────────────
SITE_URL = os.getenv('SITE_URL', 'https://listojo.com')

# ── Cache (DB-backed — shared across gunicorn workers, no Redis needed) ────────
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.db.DatabaseCache',
        'LOCATION': 'listojo_cache',
    }
}

# ── Cloudflare Turnstile (bot protection on signup) ───────────────────────────
# Fail-open: when keys are absent, the CAPTCHA check is skipped.
TURNSTILE_SITE_KEY   = os.getenv('TURNSTILE_SITE_KEY', '')
TURNSTILE_SECRET_KEY = os.getenv('TURNSTILE_SECRET_KEY', '')

# ── Twilio (phone verification + SMS notifications) ───────────────────────────
TWILIO_ACCOUNT_SID        = os.getenv('TWILIO_ACCOUNT_SID', '')
TWILIO_AUTH_TOKEN         = os.getenv('TWILIO_AUTH_TOKEN', '')
TWILIO_VERIFY_SERVICE_SID = os.getenv('TWILIO_VERIFY_SERVICE_SID', '')   # for OTP (Verify)
TWILIO_SMS_FROM           = os.getenv('TWILIO_SMS_FROM', '')             # sender number for SMS

# ── Realty Mole (RapidAPI) ────────────────────────────────────────────────────
REALTY_MOLE_API_KEY = os.getenv('REALTY_MOLE_API_KEY', '')

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
    # Railway (and most proxies) terminate SSL externally and forward plain HTTP
    # internally. Trust the X-Forwarded-Proto header so Django knows the real
    # protocol is HTTPS and won't redirect-loop.
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
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
