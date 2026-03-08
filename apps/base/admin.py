from django.contrib import admin
from django.contrib.sessions.models import Session
from django.utils.safestring import mark_safe
from django.contrib.auth.models import User
import json
from .models import *

class SessionAdmin(admin.ModelAdmin):
    list_display = ['session_key', 'user', 'expire_date']
    readonly_fields = ['session_data_pretty']
    ordering = ['-expire_date']
    search_fields = ['user']  # Placeholder for username search (custom logic)

    def session_data_pretty(self, obj):
        try:
            session_data = obj.get_decoded()
            return mark_safe(f"<pre>{json.dumps(session_data, indent=4)}</pre>")
        except Exception as e:
            return str(e)

    def user(self, obj):
        session_data = obj.get_decoded()
        user_id = session_data.get('_auth_user_id')
        if user_id:
            try:
                user = User.objects.get(id=user_id)
                return user.username
            except User.DoesNotExist:
                return "Unknown User"
        return "Anonymous"

    # Custom search to filter sessions by username
    def get_search_results(self, request, queryset, search_term):
        try:
            users = User.objects.filter(username__icontains=search_term)
            user_ids = [user.id for user in users]
            session_keys = []
            for session in queryset:
                session_data = session.get_decoded()
                if session_data.get('_auth_user_id') in map(str, user_ids):
                    session_keys.append(session.session_key)
            queryset = queryset.filter(session_key__in=session_keys)
        except Exception as e:
            self.message_user(request, f"Search error: {str(e)}")
        return queryset, False

@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'english_time_minutes', 'math_time_minutes', 'is_offline_user', 'created_at', 'updated_at']
    list_filter = ['created_at', 'updated_at']
    search_fields = ['user__username', 'user__first_name', 'user__last_name']
    readonly_fields = ['created_at', 'updated_at']
    
    def is_offline_user(self, obj):
        return obj.is_offline_user()
    is_offline_user.boolean = True
    is_offline_user.short_description = 'Is Offline User'

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('user')

admin.site.register(Session, SessionAdmin)
admin.site.register(EmailVerification)

