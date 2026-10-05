from django.contrib import admin
from .models import LeaveRequest


@admin.register(LeaveRequest)
class LeaveRequestAdmin(admin.ModelAdmin):
    list_display = ('employee', 'from_date', 'to_date', 'days', 'status', 'created_at')
    list_filter = ('status', 'from_date')
    search_fields = ('employee__name', 'employee__emp_id')
    date_hierarchy = 'from_date'
    actions = ['approve_leaves', 'reject_leaves']

    def approve_leaves(self, request, queryset):
        queryset.update(status='approved')
        self.message_user(request, f'{queryset.count()} টি leave approved করা হয়েছে।')
    approve_leaves.short_description = '✅ Approve selected'

    def reject_leaves(self, request, queryset):
        queryset.update(status='rejected')
        self.message_user(request, f'{queryset.count()} টি leave rejected করা হয়েছে।')
    reject_leaves.short_description = '❌ Reject selected'