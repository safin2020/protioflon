from django import forms
from .models import ContentLog


class ContentLogForm(forms.ModelForm):
    class Meta:
        model = ContentLog
        fields = ['log_date', 'content_title', 'category', 'assist', 'item_type',
                  'cp', 'reporter', 'editor', 'panel', 'status', 'remark']
        widgets = {
            'log_date': forms.DateInput(attrs={'type': 'date'}),
            'content_title': forms.Textarea(attrs={'rows': 2,
                'placeholder': 'Content  headline ...'}),
            'remark': forms.Textarea(attrs={'rows': 2,
                'placeholder': 'Additional Comment...'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # সব field optional
        for field in self.fields.values():
            field.required = False