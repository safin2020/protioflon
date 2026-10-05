from django.urls import path
from . import views

urlpatterns = [
    path('', views.notification_list, name='notification_list'),
    path('<int:pk>/read/', views.mark_read, name='notification_read'),
    path('mark-all/', views.mark_all_read, name='notification_mark_all'),
    path('api/unread/', views.unread_count_api, name='notification_unread_api'),
]