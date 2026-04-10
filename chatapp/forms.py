from django import forms

from .models import ChatMessage, GuestChatMessage


class MessageForm(forms.ModelForm):
    class Meta:
        model = ChatMessage
        fields = ['message']
        widgets = {'message': forms.Textarea(attrs={'rows': 3})}


class GuestMessageForm(forms.ModelForm):
    class Meta:
        model = GuestChatMessage
        fields = ['guest_name', 'guest_email', 'message']
        widgets = {'message': forms.Textarea(attrs={'rows': 4})}
