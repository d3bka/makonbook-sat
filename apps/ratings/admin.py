from django.contrib import admin

from .models import RatingAssessment, RatingConfig, RatingProfile


@admin.register(RatingConfig)
class RatingConfigAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return not RatingConfig.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(RatingProfile)
class RatingProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "public_visible", "parent_access_code", "updated_at")
    list_filter = ("public_visible",)
    search_fields = ("user__username", "user__first_name", "user__last_name", "parent_access_code")
    readonly_fields = ("parent_access_code", "created_at", "updated_at")


@admin.register(RatingAssessment)
class RatingAssessmentAdmin(admin.ModelAdmin):
    list_display = ("student", "classroom", "teacher", "mean_display", "assessed_at")
    list_filter = ("classroom", "teacher", "assessed_at")
    search_fields = ("student__username", "student__first_name", "student__last_name", "classroom__name")
    date_hierarchy = "assessed_at"
    list_select_related = ("student", "classroom", "teacher")

    @admin.display(description="Mean")
    def mean_display(self, obj):
        return f"{obj.mean_score:.2f}"
