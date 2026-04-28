from django.db.utils import OperationalError
from django.http import HttpResponseRedirect
from django.shortcuts import render

# Subdomain → portal home mapping
_SUBDOMAIN_HOME = {
    'adminportal': '/portal/',
    'agenthub':    '/portal/agent/',
}


class SubdomainPortalMiddleware:
    """
    Visiting adminportal.listojo.com or agenthub.listojo.com at the site
    root redirects directly into the corresponding portal section.
    All other paths on those subdomains are served normally so that in-portal
    navigation (login, individual pages, AJAX calls) works without rewrites.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        host = request.META.get('HTTP_HOST', '').lower().split(':')[0]
        parts = host.split('.')
        # Only act when a real subdomain is present (e.g. adminportal.listojo.com)
        subdomain = parts[0] if len(parts) >= 3 else ''

        home = _SUBDOMAIN_HOME.get(subdomain)
        if home and request.path in ('/', ''):
            return HttpResponseRedirect(home)

        return self.get_response(request)


class DatabaseNotReadyMiddleware:
    """Render a helpful setup screen when migrations haven't been run yet."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        try:
            return self.get_response(request)
        except OperationalError as exc:
            if 'no such table' in str(exc).lower():
                return render(request, 'db_not_ready.html', status=503)
            raise
