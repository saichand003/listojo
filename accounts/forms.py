from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User


class RegistrationForm(UserCreationForm):
    first_name = forms.CharField(max_length=30, required=True, label='First name')
    last_name = forms.CharField(max_length=30, required=False, label='Last name')

    class Meta:
        model = User
        fields = ('first_name', 'last_name', 'username', 'email')
