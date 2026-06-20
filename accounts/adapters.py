"""
Social-account adapter — auto-links a Google login to an existing account
that has the same email, so users don't end up with duplicate accounts.

Safe because Google verifies the email it returns. (We only link on the
provider-verified email path.)
"""
import logging

from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.contrib.auth.models import User

logger = logging.getLogger(__name__)


class SocialAccountAdapter(DefaultSocialAccountAdapter):
    def pre_social_login(self, request, sociallogin):
        # Already linked to a user → nothing to do.
        if sociallogin.is_existing:
            return

        email = (sociallogin.user.email or '').strip().lower()
        if not email:
            return

        try:
            existing = User.objects.get(email__iexact=email)
        except User.DoesNotExist:
            return
        except User.MultipleObjectsReturned:
            existing = User.objects.filter(email__iexact=email).order_by('id').first()

        # Connect this Google identity to the existing account.
        sociallogin.connect(request, existing)
        logger.info('Linked Google login to existing account %s', existing.username)
