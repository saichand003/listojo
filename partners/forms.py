from django import forms

from partners.models import AssistedOnboardingRequest

_MAX_UPLOAD_BYTES = 5 * 1024 * 1024


class InventoryUploadForm(forms.Form):
    csv_file = forms.FileField(label='Inventory CSV')

    def clean_csv_file(self):
        upload = self.cleaned_data['csv_file']
        if not upload.name.lower().endswith('.csv'):
            raise forms.ValidationError('Please upload a .csv file.')
        if upload.size > _MAX_UPLOAD_BYTES:
            raise forms.ValidationError('That file is larger than 5 MB. Contact us and we will '
                                        'set up an automated feed instead.')
        return upload


class AssistedOnboardingForm(forms.ModelForm):
    """
    Blueprint §21/§19. Deliberately asks business questions, never "what is your
    feed URL" — a property manager should not have to solve the integration.
    """

    PMS_CHOICES = [
        ('', 'Select…'),
        ('RealPage', 'RealPage'),
        ('Yardi', 'Yardi'),
        ('Entrata', 'Entrata'),
        ('AppFolio', 'AppFolio'),
        ('Other', 'Other'),
        ('Unknown', "I don't know"),
    ]

    pms_name = forms.ChoiceField(choices=PMS_CHOICES, required=False,
                                 label='Which property-management system do you use?')

    class Meta:
        model = AssistedOnboardingRequest
        fields = ['pms_name', 'syndicates_elsewhere', 'syndication_targets',
                  'syndication_vendor', 'technical_contact_name',
                  'technical_contact_email', 'notes']
        labels = {
            'syndicates_elsewhere': 'Do your listings already post automatically to other sites?',
            'syndication_targets': 'Which sites receive them?',
            'syndication_vendor': 'Do you use a separate syndication vendor?',
            'technical_contact_name': 'Who manages your listing software?',
            'technical_contact_email': 'Their email',
            'notes': 'Anything else we should know?',
        }
        widgets = {
            'syndication_targets': forms.TextInput(
                attrs={'placeholder': 'Zillow, Apartments.com, Zumper…'}),
            'syndication_vendor': forms.TextInput(attrs={'placeholder': 'If you know it'}),
            'notes': forms.Textarea(attrs={'rows': 3}),
        }
