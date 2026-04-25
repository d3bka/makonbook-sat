from django.contrib import admin
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.html import format_html

from .forms import APMultipleChoiceQuestionForm
from .models import (
    APClass,
    APExamAnswer,
    APExamAttempt,
    APExamEvent,
    APFRQPage,
    APFRQSubmission,
    APMockExam,
    APMultipleChoiceQuestion,
)


class APMultipleChoiceQuestionInline(admin.TabularInline):
    model = APMultipleChoiceQuestion
    extra = 1
    fields = ("part", "number", "question", "a", "b", "c", "d", "e", "correct_answer")
    ordering = ("part", "number")


class APFRQPageInline(admin.TabularInline):
    model = APFRQPage
    extra = 1
    fields = ("page_number", "title", "image", "file", "instructions")
    ordering = ("page_number",)


@admin.register(APClass)
class APClassAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "is_active", "updated_at")
    list_filter = ("is_active", "groups")
    search_fields = ("name", "code", "description")
    filter_horizontal = ("groups",)


@admin.register(APMockExam)
class APMockExamAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "ap_class",
        "status",
        "part_a_count",
        "part_b_count",
        "frq_count",
        "part_a_duration_minutes",
        "part_b_duration_minutes",
        "frq_duration_minutes",
        "updated_at",
    )
    list_filter = ("status", "ap_class", "groups")
    search_fields = ("title", "slug", "description", "rules")
    prepopulated_fields = {"slug": ("title",)}
    filter_horizontal = ("groups",)
    list_editable = ("status",)
    inlines = [APMultipleChoiceQuestionInline, APFRQPageInline]
    fieldsets = (
        ("Exam", {"fields": ("title", "slug", "ap_class", "description", "rules", "groups", "status", "created_by")}),
        ("Durations", {"fields": ("part_a_duration_minutes", "part_b_duration_minutes", "frq_duration_minutes")}),
        ("Display", {"fields": ("show_score_immediately",)}),
    )

    def part_a_count(self, obj):
        return obj.part_a_questions_count

    def part_b_count(self, obj):
        return obj.part_b_questions_count

    def frq_count(self, obj):
        return obj.frq_pages_count

    def save_model(self, request, obj, form, change):
        if not obj.created_by_id:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(APMultipleChoiceQuestion)
class APMultipleChoiceQuestionAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "exam",
        "part",
        "number",
        "short_question",
        "correct_answer",
        "desmos_allowed",
        "updated_at",
    ]
    list_filter = ("exam", "part", "desmos_allowed")
    search_fields = ("exam__title", "question", "passage", "a", "b", "c", "d", "e")
    autocomplete_fields = ("exam",)
    form = APMultipleChoiceQuestionForm
    ordering = ("exam", "part", "number")
    change_form_template = "admin/apclasses/ap_multiple_choice_question/change_form.html"

    fieldsets = (
        ("Basic Information", {
            "fields": ("exam", "part", "number")
        }),
        ("Question Content", {
            "fields": ("question", "passage", "image")
        }),
        ("Answer Choices", {
            "fields": (("a", "image_a"), ("b", "image_b"), ("c", "image_c"), ("d", "image_d"), ("e", "image_e"))
        }),
        ("Answer and Explanation", {
            "fields": ("correct_answer", "explanation")
        }),
        ("AP Part Rules", {
            "fields": ("calculator_allowed", "desmos_allowed")
        }),
    )
    readonly_fields = ("calculator_allowed", "desmos_allowed")

    def short_question(self, obj):
        value = obj.question or obj.passage or ""
        return value[:80]

    short_question.short_description = "Question"

    def response_change(self, request, obj):
        if "_save_and_next" in request.POST:
            next_question = self.get_next_question(obj)
            if next_question:
                return redirect(reverse("admin:apclasses_apmultiplechoicequestion_change", args=(next_question.pk,)))
        return super().response_change(request, obj)

    def get_next_question(self, obj):
        return APMultipleChoiceQuestion.objects.filter(
            exam=obj.exam,
            part=obj.part,
            number__gt=obj.number
        ).order_by("number").first()

    def change_view(self, request, object_id, form_url='', extra_context=None):
        extra_context = extra_context or {}
        extra_context['show_save_and_next'] = True
        return super().change_view(request, object_id, form_url, extra_context)


@admin.register(APFRQPage)
class APFRQPageAdmin(admin.ModelAdmin):
    list_display = ("exam", "page_number", "title", "preview", "updated_at")
    list_filter = ("exam",)
    search_fields = ("exam__title", "title", "instructions")
    autocomplete_fields = ("exam",)

    def preview(self, obj):
        if obj.image:
            return format_html('<img src="{}" style="height:60px;max-width:120px;object-fit:cover;border-radius:6px;" />', obj.image.url)
        if obj.file:
            return format_html('<a href="{}" target="_blank">Open file</a>', obj.file.url)
        return "—"


@admin.register(APExamEvent)
class APExamEventAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "exam",
        "slug",
        "status",
        "is_public",
        "is_global",
        "always_live",
        "show_score_immediately",
        "show_leaderboard",
        "start_at",
        "end_at",
    )
    search_fields = ("title", "slug", "exam__title")
    list_filter = ("status", "is_public", "is_global", "always_live", "show_score_immediately", "show_leaderboard")
    autocomplete_fields = ("exam",)
    list_editable = ("show_score_immediately", "show_leaderboard", "status", "is_public", "is_global", "always_live")
    fieldsets = (
        ("Event", {"fields": ("title", "slug", "exam", "description", "rules")}),
        ("Access", {"fields": ("access_code", "is_public", "is_global")}),
        ("Availability", {"fields": ("status", "always_live", "start_at", "end_at")}),
        ("Options", {"fields": ("allow_resume", "show_score_immediately", "show_leaderboard")}),
    )


class APExamAnswerInline(admin.TabularInline):
    model = APExamAnswer
    extra = 0
    readonly_fields = ("question", "selected_answer", "is_correct", "answered_at")
    can_delete = False


class APFRQSubmissionInline(admin.TabularInline):
    model = APFRQSubmission
    extra = 0
    fields = ("page_number", "image", "file", "score", "teacher_comment", "uploaded_at")
    readonly_fields = ("uploaded_at",)


@admin.register(APExamAttempt)
class APExamAttemptAdmin(admin.ModelAdmin):
    list_display = ("event", "student", "status", "score", "raw_score", "answered_questions", "total_questions", "started_at", "submitted_at")
    list_filter = ("status", "event")
    search_fields = ("student__username", "student__first_name", "student__last_name", "event__title")
    readonly_fields = ("token", "started_at")
    inlines = [APExamAnswerInline, APFRQSubmissionInline]


@admin.register(APExamAnswer)
class APExamAnswerAdmin(admin.ModelAdmin):
    list_display = ("attempt", "question", "selected_answer", "is_correct", "answered_at")
    list_filter = ("is_correct", "question__part", "attempt__event")
    search_fields = ("attempt__student__username", "attempt__event__title", "question__question")


@admin.register(APFRQSubmission)
class APFRQSubmissionAdmin(admin.ModelAdmin):
    list_display = ("attempt", "page_number", "score", "uploaded_at")
    list_filter = ("attempt__event",)
    search_fields = ("attempt__student__username", "attempt__event__title", "teacher_comment")
