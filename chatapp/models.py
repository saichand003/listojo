from django.contrib.auth.models import User
from django.db import models


class ChatMessage(models.Model):
    sender = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sent_messages')
    recipient = models.ForeignKey(User, on_delete=models.CASCADE, related_name='received_messages')
    message = models.TextField()
    sent_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['sent_at']

    def __str__(self):
        return f'{self.sender} -> {self.recipient}'


class GuestChatMessage(models.Model):
    recipient = models.ForeignKey(User, on_delete=models.CASCADE, related_name='guest_messages')
    sender_user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name='guest_chat_messages',
        null=True,
        blank=True,
    )
    guest_name = models.CharField(max_length=120)
    guest_email = models.EmailField()
    message = models.TextField()
    sent_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-sent_at']

    def __str__(self):
        return f'{self.guest_name} -> {self.recipient}'
