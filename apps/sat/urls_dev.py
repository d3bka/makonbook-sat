from django.urls import path
from . import views_dev

# URLs specific to the Dev Mode
urlpatterns = [
    path('', views_dev.dev_dashboard, name='dev_dashboard'),
    path('search-questions/', views_dev.search_questions, name='dev_search_questions'),
    path('manage-groups/', views_dev.manage_groups, name='dev_manage_groups'),
    path('create-bulk-users/', views_dev.create_bulk_users, name='dev_create_bulk_users'),
    path('assign-test/', views_dev.assign_test, name='dev_assign_test'),
    path('test-statistics/', views_dev.test_statistics, name='dev_test_statistics'),
    # Add other dev-specific URLs here
] 