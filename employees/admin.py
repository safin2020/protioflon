from django.contrib import admin
from .models import Employee, OfficeSetting


@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ('emp_id', 'name', 'designation', 'department', 'duty_group', 'status', 'user')
    search_fields = ('name', 'emp_id', 'mobile', 'nid')
    list_filter = ('status', 'duty_group', 'department')
    fields = ('user', 'name', 'photo', 'designation', 'department', 'joining_date',
              'mobile', 'email', 'address', 'salary', 'duty_group', 'status',
              'emergency1_name', 'emergency1_mobile',
              'emergency2_name', 'emergency2_mobile',
              'nid', 'father_nid', 'mother_nid')


@admin.register(OfficeSetting)
class OfficeSettingAdmin(admin.ModelAdmin):
    list_display = ('title', 'office_radius')