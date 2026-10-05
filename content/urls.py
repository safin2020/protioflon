from django.urls import path
from . import views

urlpatterns = [
    path('', views.log_list, name='content_log'),
    path('add/', views.log_add, name='content_log_add'),
    path('<int:pk>/edit/', views.log_edit, name='content_log_edit'),
    path('download/csv/', views.log_csv, name='content_log_csv'),
    path('download/pdf/', views.log_pdf, name='content_log_pdf'),
    path('report/', views.content_report, name='content_report'),
     path('report/pdf/', views.content_report_pdf, name='content_report_pdf'),  
]