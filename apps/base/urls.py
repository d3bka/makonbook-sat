# base/urls.py
from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('login/', views.loginUser, name='login'),
    path('logout/', views.logoutUser, name='logout'),
    path('register/', views.register, name='register'),
    path('forgot-password/', views.forgot_password, name='forgot_password'),
    path('reset-password/', views.password_reset_confirm, name='password_reset_confirm'),
    path('activate/<uuid:token>/', views.activate, name='activate'),
    path('edit-profile/', views.edit_profile, name='edit_profile'),  # Ensure this line exists
    path('software/', views.software, name='software'),
    path('report-issue/', views.submit_general_issue_report, name='submit_general_issue_report'),
]