from django.contrib.auth.signals import user_logged_in
from django.dispatch import receiver


@receiver(user_logged_in)
def stamp_fresh_login(sender, request, user, **kwargs):
    request.session['show_saved_search_banner'] = True
