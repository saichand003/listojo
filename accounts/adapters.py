"""
Social-account adapter:
  • Auto-links a Google login to an existing same-email account (no duplicates).
  • Backfills first/last name from Google on link AND on every social login,
    so accounts always show a real name (Google returns given_name/family_name
    via the `profile` scope).

Safe because Google verifies the email it returns.
"""
import logging

from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.contrib.auth.models import User

logger = logging.getLogger(__name__)


def _fill_name(user, extra):
    """Set first/last name from Google data when missing. Returns True if changed."""
    changed = False
    if not user.first_name and extra.get('given_name'):
        user.first_name = extra['given_name']
        changed = True
    if not user.last_name and extra.get('family_name'):
        user.last_name = extra['family_name']
        changed = True
    if changed and user.pk:
        user.save(update_fields=['first_name', 'last_name'])
    return changed


class SocialAccountAdapter(DefaultSocialAccountAdapter):
    def pre_social_login(self, request, sociallogin):
        extra = sociallogin.account.extra_data or {}

        # Already linked to a user → just make sure the name is filled in.
        if sociallogin.is_existing:
            _fill_name(sociallogin.user, extra)
            return

        # Not linked yet: connect to an existing same-email account if one exists.
        email = (sociallogin.user.email or '').strip().lower()
        if not email:
            return
        try:
            existing = User.objects.get(email__iexact=email)
        except User.DoesNotExist:
            return
        except User.MultipleObjectsReturned:
            existing = User.objects.filter(email__iexact=email).order_by('id').first()

        _fill_name(existing, extra)
        sociallogin.connect(request, existing)
        logger.info('Linked Google login to existing account %s', existing.username)
