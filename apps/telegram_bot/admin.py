from django.contrib import admin
from .models import TelegramAdmin, BulkUserRequest, GeneratedUser


@admin.register(TelegramAdmin)
class TelegramAdminAdmin(admin.ModelAdmin):
    list_display = ['telegram_id', 'username', 'first_name', 'last_name', 'is_admin', 'is_support', 'is_active', 'created_at']
    list_filter = ['is_admin', 'is_support', 'is_active', 'created_at']
    search_fields = ['telegram_id', 'username', 'first_name', 'last_name']
    list_editable = ['is_admin', 'is_support', 'is_active']
    ordering = ['-created_at']


@admin.register(BulkUserRequest)
class BulkUserRequestAdmin(admin.ModelAdmin):
    list_display = ['id', 'telegram_admin', 'prefix', 'count', 'status', 'created_at', 'completed_at']
    list_filter = ['status', 'created_at', 'telegram_admin']
    search_fields = ['prefix', 'telegram_admin__username']
    readonly_fields = ['created_at', 'completed_at']
    ordering = ['-created_at']
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('telegram_admin')


@admin.register(GeneratedUser)
class GeneratedUserAdmin(admin.ModelAdmin):
    list_display = ['username', 'password', 'bulk_request', 'created_at']
    list_filter = ['created_at', 'bulk_request__telegram_admin']
    search_fields = ['username', 'user__username']
    readonly_fields = ['created_at']
    ordering = ['-created_at']
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('bulk_request', 'user')