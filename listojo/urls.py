from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.templatetags.static import static as static_url
from django.urls import include, path
from django.views.generic.base import RedirectView


class FaviconRedirect(RedirectView):
    """
    Serve /favicon.ico from the hashed static file.

    Crawlers (Google's included) probe the site root for this path and ignore
    the <link> tags when they do. Static filenames are content-hashed by
    ManifestStaticFilesStorage, so the target is resolved per request rather
    than at import time — the manifest does not exist yet during collectstatic.
    """
    permanent = True

    def get_redirect_url(self, *args, **kwargs):
        return static_url('img/favicon.ico')


urlpatterns = [
    path('favicon.ico', FaviconRedirect.as_view()),
    path('admin/', admin.site.urls),
    path('accounts/', include('accounts.urls')),
    path('accounts/', include('django.contrib.auth.urls')),
    path('accounts/', include('allauth.urls')),
    path('chat/', include('chatapp.urls')),
    path('', include('listings.urls')),
    path('portal/', include('portal.urls')),
    path('partners/', include('partners.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
