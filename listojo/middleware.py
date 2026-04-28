from django.db.utils import OperationalError
from django.shortcuts import render


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
