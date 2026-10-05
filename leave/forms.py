from django import forms
from django.core.exceptions import ValidationError
from .models import LeaveRequest


ALLOWED_DOCS = [
    'application/pdf',
    'image/jpeg', 'image/png', 'image/webp',
    'application/msword',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
]
MAX_SIZE = 5 * 1024 * 1024


def validate_attachment(file):
    if file.content_type not in ALLOWED_DOCS:
        raise ValidationError('only PDF, Word or Image File Applicable')
    if file.size > MAX_SIZE:
        raise ValidationError(f'File size not more than 5MB')


class LeaveForm(forms.ModelForm):
    class Meta:
        model = LeaveRequest
        fields = ['from_date', 'to_date', 'reason', 'attachment']
        widgets = {
            'from_date': forms.DateInput(attrs={'type': 'date', 'id': 'from_date', 'style': 'display:none;'}),
            'to_date': forms.DateInput(attrs={'type': 'date', 'id': 'to_date', 'style': 'display:none;'}),
            'reason': forms.Textarea(attrs={'rows': 3, 'placeholder': 'Describe why you need leave...'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # from_date এবং to_date কে optional করুন
        self.fields['from_date'].required = False
        self.fields['to_date'].required = False

    def clean(self):
        cleaned = super().clean()
        f = cleaned.get('from_date')
        t = cleaned.get('to_date')
        # শুধু validation করুন যদি দুটোই থাকে
        if f and t and t < f:
            raise forms.ValidationError('End date cannot be before start date.')
        return cleaned

    def clean_attachment(self):
        att = self.cleaned_data.get('attachment')
        if att:
            validate_attachment(att)
        return att