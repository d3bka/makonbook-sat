from django.urls import path
from . import views_admin

urlpatterns = [
    path('', views_admin.admin_dashboard, name='admin_dashboard'),

    # Users
    path('users/', views_admin.admin_users, name='admin_users'),
    path('users/<int:user_id>/', views_admin.admin_user_detail, name='admin_user_detail'),
    path('users/<int:user_id>/edit/', views_admin.admin_user_edit, name='admin_user_edit'),
    path('users/<int:user_id>/delete/', views_admin.admin_user_delete, name='admin_user_delete'),

    # Groups
    path('groups/', views_admin.admin_groups, name='admin_groups'),
    path('groups/<int:group_id>/', views_admin.admin_group_detail, name='admin_group_detail'),
    path('groups/<int:group_id>/delete/', views_admin.admin_group_delete, name='admin_group_delete'),
    path('groups/<int:group_id>/remove-user/<int:user_id>/', views_admin.admin_group_remove_user, name='admin_group_remove_user'),

    # Tests
    path('tests/', views_admin.admin_tests, name='admin_tests'),
    path('tests/<str:test_name>/', views_admin.admin_test_detail, name='admin_test_detail'),

    # Mocks
    path('mocks/', views_admin.admin_mocks, name='admin_mocks'),
    path('mocks/create/', views_admin.admin_mock_create, name='admin_mock_create'),
    path('mocks/<int:mock_id>/', views_admin.admin_mock_detail, name='admin_mock_detail'),
    path('mocks/<int:mock_id>/download/', views_admin.admin_mock_download, name='admin_mock_download'),

    # Assign Tests to Groups
    path('groups/<int:group_id>/edit-tests/', views_admin.edit_group_tests, name='edit_group_tests'),
    
    # User Create
    path('users/create/', views_admin.admin_user_create, name='admin_user_create'),

    #Mock Deletion
    path('mocks/<int:mock_id>/delete/', views_admin.admin_mock_delete, name='admin_mock_delete'),
]
