from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver

from accounts.models import UserProfile


@receiver(post_save, sender=User)
def ensure_user_profile(sender, instance, created, **kwargs):
    """Every User has exactly one UserProfile."""
    if created:
        UserProfile.objects.get_or_create(user=instance)
    else:
        # Back-fill for users created before profiles existed
        UserProfile.objects.get_or_create(user=instance)
