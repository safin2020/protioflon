from datetime import date
from django.contrib import messages
from django.contrib.auth import (authenticate, login as auth_login,
                                 logout as auth_logout, update_session_auth_hash)
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.core.cache import cache
from django.shortcuts import render, redirect
from employees.models import Employee, OfficeSetting
from attendance.models import Attendance
from leave.models import LeaveRequest
from .models import Profile


def login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')

    def get_client_ip():
        xff = request.META.get('HTTP_X_FORWARDED_FOR')
        if xff:
            return xff.split(',')[0].strip()
        return request.META.get('REMOTE_ADDR', 'unknown')

    ip = get_client_ip()
    lock_key = f'lock:{ip}'
    fail_key = f'fail:{ip}'

    if cache.get(lock_key):
        messages.error(request, '🔒 অনেকবার ভুল চেষ্টা করেছেন। ১৫ মিনিট পরে আবার চেষ্টা করুন।')
        return render(request, 'login.html', {'office': OfficeSetting.load()})

    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        user = authenticate(request, username=username, password=password)
        if user:
            cache.delete(fail_key)
            cache.delete(lock_key)
            auth_login(request, user)
            return redirect('dashboard')

        fails = cache.get(fail_key, 0) + 1
        cache.set(fail_key, fails, timeout=15 * 60)
        remaining = 5 - fails

        if fails >= 5:
            cache.set(lock_key, True, timeout=15 * 60)
            messages.error(request, '🔒 ৫ বার ভুল password — IP ১৫ মিনিটের জন্য blocked.')
        else:
            messages.error(request, f'ভুল username/password। আর {remaining} বার চেষ্টা বাকি।')

    return render(request, 'login.html', {'office': OfficeSetting.load()})


def forgot_password(request):
    from django.contrib.auth.models import User
    if request.user.is_authenticated:
        return redirect('dashboard')
    if request.method == 'POST':
        ident = (request.POST.get('username') or '').strip()
        emp_code = (request.POST.get('emp_code') or '').strip()
        mobile = (request.POST.get('mobile') or '').strip()
        pw1 = request.POST.get('new_password1') or ''
        pw2 = request.POST.get('new_password2') or ''

        user = (User.objects.filter(username__iexact=ident).first()
                or User.objects.filter(email__iexact=ident).first())
        emp = getattr(user, 'employee', None) if user else None

        ok = False
        if user and emp:
            if emp_code and emp.emp_id.lower() == emp_code.lower():
                ok = True
            if mobile and mobile in (emp.mobile, emp.emergency1_mobile):
                ok = True

        if not ok:
            messages.error(request, 'তথ্য মেলেনি — সঠিক Username + Employee ID বা registered mobile দিন।')
        elif len(pw1) < 8:
            messages.error(request, 'Password কমপক্ষে ৮ অক্ষরের হতে হবে।')
        elif pw1 != pw2:
            messages.error(request, 'দুটি password মিলছে না।')
        else:
            user.set_password(pw1)
            user.save()
            messages.success(request, '✅ Password বদলে গেছে — এখন নতুন password দিয়ে login করুন।')
            return redirect('login')
    return render(request, 'forgot.html')


def logout_view(request):
    auth_logout(request)
    return redirect('login')


@login_required
def dashboard_view(request):
    prof = getattr(request.user, 'profile', None)
    if not prof:
        prof, _ = Profile.objects.get_or_create(
            user=request.user,
            defaults={'role': 'admin' if request.user.is_superuser else 'employee'})
    elif request.user.is_superuser and prof.role != 'admin':
        prof.role = 'admin'
        prof.save()

    emp = getattr(request.user, 'employee', None)
    display_name = emp.name if emp else (request.user.get_full_name() or request.user.username)
    today = date.today()
    att = Attendance.objects.filter(date=today)

    # Mojo বাদ দিয়ে counts
    active_tracking = Employee.objects.filter(status='active').exclude(duty_group='mojo')

    joinees = []
    for e in Employee.objects.filter(status='active').order_by('-joining_date')[:5]:
        parts = e.name.split()
        joinees.append({'emp': e,
                        'initials': ''.join(p[0] for p in parts[:2]).upper() or e.name[:2].upper()})

    activities = []
    for a in Attendance.objects.select_related('employee').order_by('-id')[:6]:
        d = a.date.strftime('%d %b, %Y')
        if a.status == 'present' and a.check_out:
            activities.append({'icon': 'fa-sign-out-alt', 'bg': '#dbeafe', 'fg': '#1d4ed8',
                               'text': f'{a.employee.name} checked out',
                               'sub': f"{d} • {a.check_out.strftime('%I:%M %p')}"})
        elif a.status == 'present' and a.check_in:
            activities.append({'icon': 'fa-sign-in-alt', 'bg': '#d1fae5', 'fg': '#047857',
                               'text': f'{a.employee.name} checked in',
                               'sub': f"{d} • {a.check_in.strftime('%I:%M %p')}"})
        elif a.status == 'wfh':
            activities.append({'icon': 'fa-home', 'bg': '#e0e7ff', 'fg': '#3730a3',
                               'text': f'{a.employee.name} — Work From Home', 'sub': d})
        elif a.status == 'absent':
            activities.append({'icon': 'fa-user-times', 'bg': '#fee2e2', 'fg': '#b91c1c',
                               'text': f'{a.employee.name} — Absent', 'sub': d})
        else:
            activities.append({'icon': 'fa-door-closed', 'bg': '#ffedd5', 'fg': '#9a3412',
                               'text': f'{a.employee.name} — Off Day', 'sub': d})
    for lv in LeaveRequest.objects.select_related('employee').order_by('-id')[:4]:
        activities.append({'icon': 'fa-calendar-check', 'bg': '#fef3c7', 'fg': '#92400e',
                           'text': f'{lv.employee.name} applied for leave',
                           'sub': f"{lv.from_date:%d %b} – {lv.to_date:%d %b} • {lv.get_status_display()}"})

    return render(request, 'dashboard.html', {
        'display_name': display_name,
        'total_employees': Employee.objects.filter(status='active').count(),
        'mojo_count': Employee.objects.filter(status='active', duty_group='mojo').count(),
        'present_today': att.filter(status='present').count(),
        'wfh_today': att.filter(status='wfh').count(),
        'absent_today': att.filter(status='absent').count(),
        'off_today': att.filter(status='off').count(),
        'on_leave': LeaveRequest.objects.filter(
            status='approved', from_date__lte=today, to_date__gte=today).count(),
        'recent_joinees': joinees,
        'activities': activities,
        'today': today,
    })


@login_required
def my_profile(request):
    emp = getattr(request.user, 'employee', None)
    prof = getattr(request.user, 'profile', None)
    role_key = 'admin' if request.user.is_superuser else (prof.role if prof else 'employee')
    role_label = role_key.title()
    initials = ''
    if emp:
        parts = emp.name.split()
        initials = ''.join(p[0] for p in parts[:2]).upper() or emp.name[:2].upper()
    elif request.user.get_full_name():
        parts = request.user.get_full_name().split()
        initials = ''.join(p[0] for p in parts[:2]).upper()
    else:
        initials = request.user.username[:2].upper()
    display_name = emp.name if emp else (request.user.get_full_name() or request.user.username)

    return render(request, 'profile.html', {
        'emp': emp, 'role_key': role_key, 'role_label': role_label,
        'initials': initials, 'display_name': display_name,
    })


@login_required
def change_password(request):
    if request.method == 'POST':
        form = PasswordChangeForm(request.user, request.POST)
        if form.is_valid():
            user = form.save()
            update_session_auth_hash(request, user)
            messages.success(request, 'Password changed successfully!')
            return redirect('my_profile')
        messages.error(request, 'Please correct the errors below.')
    else:
        form = PasswordChangeForm(request.user)
    return render(request, 'change_password.html', {'form': form})