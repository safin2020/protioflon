from django.db import models
from employees.models import Employee


class LeaveRequest(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='leaves')
    from_date = models.DateField()  # Fast Day
    to_date = models.DateField()    # Last Day
    leave_dates = models.JSONField(default=list, blank=True,
                                   help_text='.......')
    reason = models.TextField(blank=True)
    attachment = models.FileField(upload_to='leave_attachments/', blank=True, null=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    reject_reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    @property
    def days(self):
        """বিচ্ছিন্ন দিন থাকলে সেগুলোর count, না থাকলে range"""
        if self.leave_dates:
            return len(self.leave_dates)
        return (self.to_date - self.from_date).days + 1

    @property
    def date_list(self):
        """বিচ্ছিন্ন দিনের list return করে"""
        if self.leave_dates:
            return sorted(self.leave_dates)
        # পুরনো records এর জন্য range generate
        from datetime import timedelta
        dates = []
        current = self.from_date
        while current <= self.to_date:
            dates.append(current.strftime('%Y-%m-%d'))
            current += timedelta(days=1)
        return dates

    def __str__(self):
        return f"{self.employee.name} — {self.status}"