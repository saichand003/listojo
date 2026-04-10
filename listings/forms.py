from django import forms

from .models import Listing, ListingInquiry


class ListingForm(forms.ModelForm):
    class Meta:
        model = Listing
        fields = [
            'title',
            'category',
            'description',
            'price',
            'city',
            'state',
            'country',
            'contact_phone',
            'featured',
            'image',
        ]


class ListingInquiryForm(forms.ModelForm):
    class Meta:
        model = ListingInquiry
        fields = ['name', 'email', 'phone', 'message']
