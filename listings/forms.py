from django import forms

from .models import Listing, ListingInquiry

MAX_IMAGE_SIZE_MB    = 5
MAX_IMAGE_SIZE_BYTES = MAX_IMAGE_SIZE_MB * 1024 * 1024
MAX_IMAGE_COUNT      = 8


class ListingForm(forms.ModelForm):
    class Meta:
        model = Listing
        fields = [
            'title',
            'category',
            'description',
            'price',
            'price_unit',
            'address_line',
            'city',
            'state',
            'zip_code',
            'country',
            'contact_phone',
            'accommodation_type',
            'property_type',
            'bills_included',
            'security_deposit',
            'available_from',
            'featured',
            'tags',
        ]
        widgets = {
            'tags': forms.TextInput(attrs={
                'placeholder': 'e.g. pet-friendly, parking, furnished',
                'data-tag-input': 'true',
            }),
            'category': forms.Select(attrs={'required': True}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['category'].choices = [('', '— Select a category —')] + [
            c for c in self.fields['category'].choices if c[0]
        ]
        self.fields['category'].required = True


def validate_uploaded_images(files, existing_count=0):
    """Returns a list of error strings. Empty list means all OK."""
    errors = []
    total = existing_count + len(files)
    if total > MAX_IMAGE_COUNT:
        errors.append(f'Too many images. You can have at most {MAX_IMAGE_COUNT} per listing (currently have {existing_count}, trying to add {len(files)}).')
    for f in files:
        if f.size > MAX_IMAGE_SIZE_BYTES:
            errors.append(f'"{f.name}" is {f.size / 1024 / 1024:.1f} MB — maximum per image is {MAX_IMAGE_SIZE_MB} MB.')
    return errors


class ListingInquiryForm(forms.ModelForm):
    class Meta:
        model = ListingInquiry
        fields = ['name', 'email', 'phone', 'message']
