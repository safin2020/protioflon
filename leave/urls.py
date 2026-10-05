from django.urls import path
from . import views

urlpatterns = [
    # ✅ এখানে 'my/' যোগ করা হয়েছে যাতে /leave/my/ লিংক কাজ করে
    path('my/', views.my_leaves, name='my_leaves'),
    
    path('manage/', views.manage_leaves, name='manage_leaves'),
    path('<int:pk>/approve/', views.leave_approve, name='leave_approve'),
    path('<int:pk>/reject/', views.leave_reject, name='leave_reject'),
    path('download/csv/', views.leave_download_csv, name='leave_download_csv'),
    path('download/pdf/', views.leave_download_pdf, name='leave_download_pdf'),
    path('application/<int:pk>/pdf/', views.leave_application_pdf, name='leave_application_pdf'),
]