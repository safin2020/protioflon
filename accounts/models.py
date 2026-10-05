from django.conf import settings
from django.db import models

ROLE_CHOICES = [
    ('admin', 'Admin'),
    ('supervisor', 'Supervisor'),
    ('employee', 'Employee'),
]


class Profile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL,
                                on_delete=models.CASCADE,
                                related_name='profile')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='employee')

    def __str__(self):
        return f"{self.user.username} ({self.role})"