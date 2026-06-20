from django.contrib.auth.models import User
from django.db import models


class UserProfile(models.Model):
    """
    Extends the built-in User with a phone number, verification state, and
    notification preferences. Auto-created via signal when a User is created.
    """
    user           = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    phone          = models.CharField(max_length=20, blank=True, default='',
                                      help_text='E.164 format, e.g. +14695551234')
    phone_verified = models.BooleanField(default=False)

    # Notification channel preferences
    notify_email   = models.BooleanField(default=True)
    notify_sms     = models.BooleanField(default=False)

    created_at     = models.DateTimeField(auto_now_add=True)
    updated_at     = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'Profile<{self.user.username}>'

    @property
    def can_sms(self) -> bool:
        """SMS is only sendable to an opted-in, verified phone."""
        return bool(self.notify_sms and self.phone_verified and self.phone)

    @property
    def can_email(self) -> bool:
        return bool(self.notify_email and self.user.email)
