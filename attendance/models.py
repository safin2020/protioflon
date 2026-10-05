from datetime import date, timedelta
from django.db import models
from django.contrib.auth.models import User
from employees.models import Employee


class DutyHour(models.Model):
    """নির্দিষ্ট দিনের জন্য manual duty hours (admin/supervisor সেট করে)"""
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='duty_hours')
    date = models.DateField()
    hours = models.FloatField()
    remark = models.CharField(max_length=100, blank=True)
    set_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('employee', 'date')
        ordering = ['date', 'employee__emp_id']

    def __str__(self):
        return f'{self.employee.emp_id} — {self.date} — {self.hours}h'


def target_hours_for(emp, day):
    """ওই দিনের manual hours থাকলে সেটা, না থাকলে default target_hours"""
    ov = DutyHour.objects.filter(employee=emp, date=day).first()
    return ov.hours if ov else emp.target_hours


class Attendance(models.Model):
    STATUS_CHOICES = [
        ('present', 'Present'),
        ('wfh', 'Work From Home'),
        ('absent', 'Absent'),
        ('off', 'Off Day'),
    ]
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='attendances')
    date = models.DateField()
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='present')
    check_in = models.TimeField(null=True, blank=True)
    check_out = models.TimeField(null=True, blank=True)
    check_in_lat = models.FloatField(null=True, blank=True)
    check_in_lng = models.FloatField(null=True, blank=True)
    check_in_acc = models.FloatField(null=True, blank=True)
    check_in_distance = models.IntegerField(null=True, blank=True)
    remarks = models.CharField(max_length=200, blank=True)

    class Meta:
        unique_together = ('employee', 'date')
        ordering = ['-date', 'employee__emp_id']

    def __str__(self):
        return f'{self.employee.name} — {self.date} — {self.status}'

    @property
    def worked_hours(self):
        if self.status == 'present' and self.check_in and self.check_out:
            from datetime import datetime as dt
            start = dt.combine(self.date, self.check_in)
            end = dt.combine(self.date, self.check_out)
            return round(max(0, (end - start).total_seconds() / 3600), 2)
        return 0.0

    @property
    def overtime_hours(self):
        if self.status == 'present' and self.check_in and self.check_out:
            target = target_hours_for(self.employee, self.date)
            ot = self.worked_hours - target
            return round(ot, 2) if ot > 0 else 0.0
        return 0.0


class AttendanceAlert(models.Model):
    KIND_CHOICES = [
        ('out_of_range', 'Out of Range'),
        ('no_gps', 'No GPS'),
        ('late', 'Late'),
    ]
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='alerts')
    kind = models.CharField(max_length=20, choices=KIND_CHOICES)
    lat = models.FloatField(null=True, blank=True)
    lng = models.FloatField(null=True, blank=True)
    distance_m = models.IntegerField(null=True, blank=True)
    note = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.employee.name} — {self.get_kind_display()}'


class MonthlyTarget(models.Model):
    """প্রতি employee এর মাসিক target hours — manual override"""
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='monthly_targets')
    year = models.IntegerField()
    month = models.IntegerField()
    hours = models.FloatField()
    remark = models.CharField(max_length=100, blank=True)
    set_by = models.ForeignKey('auth.User', null=True, blank=True, on_delete=models.SET_NULL)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('employee', 'year', 'month')
        ordering = ['-year', '-month', 'employee__emp_id']

    def __str__(self):
        return f'{self.employee.emp_id} — {self.year}/{self.month:02d} — {self.hours}h'


def monthly_target_for(emp, year, month):
    """মাসিক target — manual override থাকলে সেটা, না থাকলে daily থেকে calculate"""
    mt = MonthlyTarget.objects.filter(employee=emp, year=year, month=month).first()
    if mt:
        return mt.hours
    
    # Auto-calculate from daily targets
    ms = date(year, month, 1)
    me = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    total = 0.0
    current = ms
    while current < me:
        total += target_hours_for(emp, current)
        current += timedelta(days=1)
    return total