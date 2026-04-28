from django import forms

from .models import Community, FloorPlan, Listing, ListingInquiry, Unit

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
            'bedrooms',
            'bathrooms',
            'square_footage',
            'floor_plan_image',
            'virtual_tour_url',
            'tags',
            # Properties-for-sale fields
            'year_built',
            'hoa_fee',
        ]
        widgets = {
            'tags': forms.TextInput(attrs={
                'placeholder': 'e.g. pet-friendly, parking, furnished',
                'data-tag-input': 'true',
            }),
            'category': forms.Select(attrs={'required': True}),
        }

    ALLOWED_CATEGORIES = {'rentals', 'properties'}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['category'].choices = [('', '— Select a category —')] + [
            c for c in self.fields['category'].choices if c[0] in self.ALLOWED_CATEGORIES
        ]
        self.fields['category'].required = True
        # Make property-specific fields optional and clearly labelled
        for f in ('square_footage', 'year_built', 'hoa_fee'):
            self.fields[f].required = False


ALLOWED_IMAGE_TYPES = {'image/jpeg', 'image/png', 'image/webp', 'image/gif'}


def validate_uploaded_images(files, existing_count=0):
    """Returns a list of error strings. Empty list means all OK."""
    errors = []
    total = existing_count + len(files)
    if total > MAX_IMAGE_COUNT:
        errors.append(f'Too many images. You can have at most {MAX_IMAGE_COUNT} per listing (currently have {existing_count}, trying to add {len(files)}).')
    for f in files:
        if f.size > MAX_IMAGE_SIZE_BYTES:
            errors.append(f'"{f.name}" is {f.size / 1024 / 1024:.1f} MB — maximum per image is {MAX_IMAGE_SIZE_MB} MB.')
        content_type = getattr(f, 'content_type', None)
        if content_type and content_type not in ALLOWED_IMAGE_TYPES:
            errors.append(f'"{f.name}" is not an allowed image type. Upload JPEG, PNG, WebP, or GIF only.')
    return errors


class ListingInquiryForm(forms.ModelForm):
    class Meta:
        model = ListingInquiry
        fields = ['name', 'email', 'phone', 'message']


class CommunityForm(forms.ModelForm):
    class Meta:
        model = Community
        fields = [
            'name', 'description', 'community_type',
            'address_line', 'city', 'state', 'zip_code', 'country',
            'contact_phone', 'contact_email', 'website',
            'community_amenities', 'in_unit_amenities',
            'pet_policy', 'parking_info', 'utilities_included',
            'lease_terms', 'special_offer', 'featured',
        ]
        widgets = {
            'description': forms.Textarea(attrs={'rows': 4}),
            'community_amenities': forms.TextInput(attrs={
                'placeholder': 'Pool, Gym, Dog Park, Rooftop, Coworking Space'
            }),
            'in_unit_amenities': forms.TextInput(attrs={
                'placeholder': 'Washer/Dryer, Dishwasher, Balcony, Walk-in Closet'
            }),
            'pet_policy': forms.TextInput(attrs={
                'placeholder': 'e.g. Dogs & cats allowed, max 50 lbs, $300 deposit'
            }),
            'parking_info': forms.TextInput(attrs={
                'placeholder': 'e.g. Covered garage $75/mo, street parking free'
            }),
            'utilities_included': forms.TextInput(attrs={
                'placeholder': 'e.g. Water, trash included. Electricity not included.'
            }),
            'lease_terms': forms.TextInput(attrs={
                'placeholder': 'e.g. 12 months, Month-to-month available'
            }),
            'special_offer': forms.TextInput(attrs={
                'placeholder': 'e.g. 1 month free on select units. Look & Lease special.'
            }),
        }


class FloorPlanForm(forms.ModelForm):
    class Meta:
        model = FloorPlan
        fields = ['name', 'bedrooms', 'bathrooms', 'square_footage', 'floor_plan_image', 'description']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 2}),
        }


class UnitForm(forms.ModelForm):
    class Meta:
        model = Unit
        fields = ['unit_number', 'floor', 'price', 'available_from', 'status', 'notes']
        widgets = {
            'available_from': forms.DateInput(attrs={'type': 'date'}),
            'notes': forms.TextInput(attrs={'placeholder': 'Optional notes'}),
        }
