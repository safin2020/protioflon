from django.urls import path
from . import views

urlpatterns = [
    path('', views.employee_list, name='employee_list'),
    path('add/', views.employee_form, name='employee_form'),
    path('edit/<int:pk>/', views.employee_form, name='employee_form'),
    path('delete/<int:pk>/', views.employee_delete, name='employee_delete'),
    path('biodata/<int:pk>/', views.employee_biodata, name='employee_biodata'),
]