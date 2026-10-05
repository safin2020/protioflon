from django import forms
from django.core.exceptions import ValidationError
from .models import Employee


def validate_image(file):
    # যদি এটি আগে থেকে আপলোড করা ফাইল হয় (ImageFieldFile), তাহলে content_type থাকে না।
    # নতুন আপলোড করা ফাইল (UploadedFile) হলেই শুধু ভ্যালিডেশন করব।
    if not hasattr(file, 'content_type'):
        return file
        
    allowed_types = ['image/jpeg', 'image/png', 'image/webp']
    max_size = 5 * 1024 * 1024  # 5MB
    
    if file.content_type not in allowed_types:
        raise ValidationError('শুধু JPG, PNG বা WebP image অনুমোদিত।')
    if file.size > max_size:
        raise ValidationError(f'Image এর size ৫MB এর বেশি হতে পারবে না।')
    
    return file


class EmployeeForm(forms.ModelForm):
    class Meta:
        model = Employee
        fields = ['name', 'photo', 'designation', 'department', 'joining_date',
                  'mobile', 'email', 'address', 'salary', 'duty_group',
                  'target_hours',
                  'status', 'emergency1_name', 'emergency1_mobile',
                  'emergency2_name', 'emergency2_mobile',
                  'nid', 'nid_image',
                  'father_nid', 'father_nid_image',
                  'mother_nid', 'mother_nid_image']
        widgets = {
            'joining_date': forms.DateInput(attrs={'type': 'date'}),
            'address': forms.Textarea(attrs={'rows': 2}),
            'target_hours': forms.NumberInput(attrs={
                'step': '0.5', 'min': '1', 'max': '24',
                'placeholder': 'যেমন: 8'
            }),
        }

    def clean_photo(self):
        photo = self.cleaned_data.get('photo')
        if photo:
            return validate_image(photo)
        return photo

    def clean_nid_image(self):
        img = self.cleaned_data.get('nid_image')
        if img:
            return validate_image(img)
        return img

    def clean_father_nid_image(self):
        img = self.cleaned_data.get('father_nid_image')
        if img:
            return validate_image(img)
        return img

    def clean_mother_nid_image(self):
        img = self.cleaned_data.get('mother_nid_image')
        if img:
            return validate_image(img)
        return img

    def clean_target_hours(self):
        h = self.cleaned_data.get('target_hours')
        if h is not None and (h < 0.5 or h > 24):
            raise ValidationError('Duty hours .৫ থেকে ২৪ এর মধ্যে হতে হবে।')
        return h