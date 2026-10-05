from django.urls import path
from . import views

urlpatterns = [
    path('board/', views.attendance_board, name='attendance_board'),
    path('stamp/<int:emp_id>/<str:action>/', views.stamp, name='stamp'),
    path('mark/<int:emp_id>/', views.mark_status, name='mark_status'),
    path('wfh-present/<int:emp_id>/', views.mark_wfh_present, name='mark_wfh_present'),
    path('alerts/', views.alerts_list, name='attendance_alerts'),
    path('my/', views.my_attendance, name='my_attendance'),
    path('my/stamp/<str:action>/', views.self_stamp, name='self_stamp'),
    path('reports/', views.attendance_reports, name='attendance_reports'),
    path('download/csv/', views.download_csv, name='download_csv'),
    path('download/pdf/', views.download_pdf, name='download_pdf'),
    
    # ✅ এই লাইনটি অবশ্যই থাকতে হবে:
    path('duty-hours/', views.duty_hours, name='duty_hours'),
    path('monthly-targets/', views.monthly_targets, name='monthly_targets'),  # ✅ নতুন
]