from django.db import models


class Employee(models.Model):
    DUTY_CHOICES = [
        ('office', 'Office'),
        ('wfh', 'Work From Home'),
        ('field', 'Field'),
        ('mojo', 'Mojo (No Attendance)'),
    ]
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('inactive', 'Inactive'),
    ]

    name = models.CharField(max_length=120)
    photo = models.ImageField(upload_to='employees/', blank=True, null=True)
    emp_id = models.CharField(max_length=20, unique=True, blank=True)
    designation = models.CharField(max_length=100)
    department = models.CharField(max_length=100)
    joining_date = models.DateField()
    mobile = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    address = models.TextField(blank=True)
    salary = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    duty_group = models.CharField(max_length=10, choices=DUTY_CHOICES, default='office')
    target_hours = models.FloatField(default=8)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='active')
    emergency1_name = models.CharField(max_length=80, blank=True, verbose_name='Emergency 1 Name')
    emergency1_mobile = models.CharField(max_length=20, blank=True, verbose_name='Emergency 1 Mobile')
    emergency2_name = models.CharField(max_length=80, blank=True, verbose_name='Emergency 2 Name')
    emergency2_mobile = models.CharField(max_length=20, blank=True, verbose_name='Emergency 2 Mobile')
    nid = models.CharField(max_length=30, blank=True, verbose_name='Employee NID')
    nid_image = models.ImageField(upload_to='nid_images/', blank=True, null=True, verbose_name='Employee NID Image')
    father_nid = models.CharField(max_length=30, blank=True, verbose_name="Father's NID")
    father_nid_image = models.ImageField(upload_to='nid_images/', blank=True, null=True, verbose_name="Father's NID Image")
    mother_nid = models.CharField(max_length=30, blank=True, verbose_name="Mother's NID")
    mother_nid_image = models.ImageField(upload_to='nid_images/', blank=True, null=True, verbose_name="Mother's NID Image")
    user = models.OneToOneField('auth.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='employee')

    class Meta:
        ordering = ['emp_id']

    def __str__(self):
        return f"{self.emp_id} — {self.name}"

    def save(self, *args, **kwargs):
        if not self.emp_id:
            last = Employee.objects.order_by('-id').first()
            n = (last.id + 1) if last else 1
            self.emp_id = f"EMP-{n:04d}"

        if self.photo:
            try:
                from PIL import Image as PILImage
                import io
                from django.core.files.base import ContentFile

                img = PILImage.open(self.photo)
                if img.mode != 'RGB':
                    img = img.convert('RGB')
                if img.width > 800 or img.height > 800:
                    img.thumbnail((800, 800), PILImage.LANCZOS)

                buffer = io.BytesIO()
                img.save(buffer, format='JPEG', quality=85, optimize=True)
                buffer.seek(0)

                name = self.photo.name
                if not name.lower().endswith(('.jpg', '.jpeg')):
                    name = name.rsplit('.', 1)[0] + '.jpg'
                self.photo.save(name, ContentFile(buffer.read()), save=False)
            except Exception:
                pass

        super().save(*args, **kwargs)


class OfficeSetting(models.Model):
    title = models.CharField(max_length=120, default='Office')
    logo = models.ImageField(upload_to='office/', blank=True, null=True)
    office_lat = models.FloatField(null=True, blank=True)
    office_lng = models.FloatField(null=True, blank=True)
    office_radius = models.IntegerField(default=200, help_text='মিটারে')

    class Meta:
        verbose_name_plural = 'Office Settings'

    def __str__(self):
        return self.title

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj