import logging

from django.contrib.auth.signals import user_logged_in
from django.db.models.signals import pre_save
from django.dispatch import receiver

from listings.models import Community, Listing
from listings.services.geocoding import geocode_instance

logger = logging.getLogger(__name__)


@receiver(user_logged_in)
def stamp_fresh_login(sender, request, user, **kwargs):
    request.session['show_saved_search_banner'] = True


@receiver(pre_save, sender=Listing)
@receiver(pre_save, sender=Community)
def geocode_on_save(sender, instance, **kwargs):
    """
    Resolve real lat/lng before the row is written.

    geocode_instance() short-circuits when the address is unchanged and coords
    already exist, so this only hits Google when something actually changed.
    Any failure is swallowed — geocoding must never block a save.
    """
    try:
        geocode_instance(instance)
    except Exception:  # noqa: BLE001 — never let geocoding break a save
        logger.exception('geocode_on_save failed for %s #%s', sender.__name__, instance.pk)
