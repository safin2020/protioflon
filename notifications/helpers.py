from django.contrib.auth.models import User
from accounts.models import Profile
from .models import Notification


def notify_user(user, message, link='', type='info'):
    """একজন user কে notification পাঠানো"""
    Notification.objects.create(user=user, message=message, link=link, type=type)


def notify_admins(message, link='', type='info'):
    """সব admin + supervisor কে notification"""
    admins = User.objects.filter(
        profile__role__in=['admin', 'supervisor']
    ).distinct()
    for u in admins:
        Notification.objects.create(user=u, message=message, link=link, type=type)


def notify_employee(emp, message, link='', type='info'):
    """Employee কে notification (যদি user থাকে)"""
    if emp and emp.user:
        Notification.objects.create(user=emp.user, message=message, link=link, type=type)