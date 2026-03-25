from django.contrib import admin
from django.utils.html import format_html
from django.db.models import Count, Avg, Q
from django.contrib.auth.models import User, Group
from django.urls import reverse
from django.utils.safestring import mark_safe
from django.db import models
import random
import string
import json
from .models import *
from .forms import EnglishQuestionForm, MathQuestionForm

# Enhanced QuestionDomain Admin
@admin.register(QuestionDomain)
class QuestionDomainAdmin(admin.ModelAdmin):
    list_display = ['name', 'english_questions_count', 'math_questions_count', 'total_questions', 'created_at']
    search_fields = ['name']
    list_filter = ['created_at', 'updated_at']
    ordering = ['name']
    
    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        return queryset.annotate(
            english_count=Count('english_question', distinct=True),
            math_count=Count('math_question', distinct=True)
        )
    
    def english_questions_count(self, obj):
        return obj.english_count
    english_questions_count.short_description = 'English Q\'s'
    english_questions_count.admin_order_field = 'english_count'
    
    def math_questions_count(self, obj):
        return obj.math_count
    math_questions_count.short_description = 'Math Q\'s'
    math_questions_count.admin_order_field = 'math_count'
    
    def total_questions(self, obj):
        total = obj.english_count + obj.math_count
        return format_html('<strong>{}</strong>', total)
    total_questions.short_description = 'Total Questions'

# Enhanced QuestionType Admin
@admin.register(QuestionType)
class QuestionTypeAdmin(admin.ModelAdmin):
    list_display = ['name', 'domain', 'english_questions_count', 'math_questions_count', 'created_at']
    list_filter = ['domain', 'created_at']
    search_fields = ['name', 'domain__name']
    ordering = ['domain__name', 'name']
    
    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        return queryset.select_related('domain').annotate(
            english_count=Count('english_question', distinct=True),
            math_count=Count('math_question', distinct=True)
        )
    
    def english_questions_count(self, obj):
        return obj.english_count
    english_questions_count.short_description = 'English Q\'s'
    
    def math_questions_count(self, obj):
        return obj.math_count
    math_questions_count.short_description = 'Math Q\'s'

# Enhanced Test Admin
@admin.register(Test)
class TestAdmin(admin.ModelAdmin):
    list_display = ['name', 'groups_display', 'total_questions', 'english_questions_count', 'math_questions_count', 
                   'reviews_count', 'average_score', 'created']
    list_filter = ['created', 'groups']
    search_fields = ['name']
    filter_horizontal = ['groups']
    ordering = ['-created']
    
    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        return queryset.prefetch_related('groups').annotate(
            english_count=Count('english_question', distinct=True),
            math_count=Count('math_question', distinct=True),
            reviews_count=Count('test_reviews', distinct=True),
            avg_score=Avg('test_reviews__score')
        )
    
    def groups_display(self, obj):
        groups = obj.groups.all()
        if groups:
            group_names = ', '.join([group.name for group in groups[:3]])
            if len(groups) > 3:
                group_names += f' (+{len(groups)-3} more)'
            return group_names
        return 'No groups'
    groups_display.short_description = 'Access Groups'
    
    def english_questions_count(self, obj):
        return obj.english_count
    english_questions_count.short_description = 'English Q\'s'
    english_questions_count.admin_order_field = 'english_count'
    
    def math_questions_count(self, obj):
        return obj.math_count
    math_questions_count.short_description = 'Math Q\'s'
    math_questions_count.admin_order_field = 'math_count'
    
    def total_questions(self, obj):
        total = obj.english_count + obj.math_count
        return format_html('<strong>{}</strong>', total)
    total_questions.short_description = 'Total Q\'s'
    
    def reviews_count(self, obj):
        return obj.reviews_count
    reviews_count.short_description = 'Reviews'
    reviews_count.admin_order_field = 'reviews_count'
    
    def average_score(self, obj):
        value = getattr(obj, "avg_score", None)
    
        if value in (None, "", "-"):
            return "-"
    
        try:
            return round(float(value))
        except (TypeError, ValueError):
            return "-"

    average_score.short_description = 'Avg Score'
    average_score.admin_order_field = 'avg_score'

# Enhanced English Question Admin
@admin.register(English_Question)
class EnglishQuestionAdmin(admin.ModelAdmin):
    list_display = ['test', 'module', 'number', 'domain', 'type', 'has_image', 'has_explanation', 'created_at']
    list_filter = ['test', 'module', 'domain', 'type', 'graph', 'created_at']
    search_fields = ['test__name', 'number', 'domain__name', 'type__name', 'question', 'passage', 'a', 'b', 'c', 'd']
    list_per_page = 50
    form = EnglishQuestionForm
    ordering = ['test', 'module', 'number']
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('test', 'module', 'number', 'domain', 'type')
        }),
        ('Question Content', {
            'fields': ('question', 'passage', 'image', 'graph')
        }),
        ('Answer Choices', {
            'fields': ('a', 'b', 'c', 'd')
        }),
        ('Answer and Explanation', {
            'fields': ('answer', 'explained')
        }),
    )
    
    def has_image(self, obj):
        return bool(obj.image)
    has_image.boolean = True
    has_image.short_description = 'Image'
    
    def has_explanation(self, obj):
        return bool(obj.explained or obj.img_explain)
    has_explanation.boolean = True
    has_explanation.short_description = 'Explanation'

# Enhanced Math Question Admin
@admin.register(Math_Question)
class MathQuestionAdmin(admin.ModelAdmin):
    list_display = ['test', 'module', 'number', 'domain', 'type', 'has_image', 'has_explanation', 'created_at']
    list_filter = ['test', 'module', 'domain', 'type', 'graph', 'choice_graph', 'written', 'created_at']
    search_fields = ['test__name', 'number', 'domain__name', 'type__name', 'question', 'passage', 'a', 'b', 'c', 'd']
    list_per_page = 50
    form = MathQuestionForm
    ordering = ['test', 'module', 'number']
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('test', 'module', 'number', 'domain', 'type')
        }),
        ('Question Content', {
            'fields': ('question', 'passage', 'image', 'graph')
        }),
        ('Answer Choices', {
            'fields': ('a', 'b', 'c', 'd', 'choice_graph', 'image_a', 'image_b', 'image_c', 'image_d')
        }),
        ('Answer and Explanation', {
            'fields': ('written', 'answer', 'explained', 'img_explain')
        }),
    )
    
    def has_image(self, obj):
        return bool(obj.image)
    has_image.boolean = True
    has_image.short_description = 'Image'
    
    def has_explanation(self, obj):
        return bool(obj.explained or obj.img_explain)
    has_explanation.boolean = True
    has_explanation.short_description = 'Explanation'

# Comprehensive TestReview Admin with Advanced Search and Filtering
class ScoreRangeFilter(admin.SimpleListFilter):
    title = 'Score Range'
    parameter_name = 'score_range'

    def lookups(self, request, model_admin):
        return (
            ('400-600', '400-600 (Below Average)'),
            ('601-800', '601-800 (Average)'),
            ('801-1000', '801-1000 (Good)'),
            ('1001-1200', '1001-1200 (Very Good)'),
            ('1201-1400', '1201-1400 (Excellent)'),
            ('1401-1600', '1401-1600 (Perfect)'),
        )

    def queryset(self, request, queryset):
        if self.value() == '400-600':
            return queryset.filter(score__gte=400, score__lte=600)
        elif self.value() == '601-800':
            return queryset.filter(score__gte=601, score__lte=800)
        elif self.value() == '801-1000':
            return queryset.filter(score__gte=801, score__lte=1000)
        elif self.value() == '1001-1200':
            return queryset.filter(score__gte=1001, score__lte=1200)
        elif self.value() == '1201-1400':
            return queryset.filter(score__gte=1201, score__lte=1400)
        elif self.value() == '1401-1600':
            return queryset.filter(score__gte=1401, score__lte=1600)
        return queryset

class UserGroupFilter(admin.SimpleListFilter):
    title = 'User Group'
    parameter_name = 'user_group'

    def lookups(self, request, model_admin):
        groups = Group.objects.all()
        return [(group.id, group.name) for group in groups] + [('no_group', 'No Group')]

    def queryset(self, request, queryset):
        if self.value() == 'no_group':
            return queryset.filter(user__groups__isnull=True)
        elif self.value():
            return queryset.filter(user__groups__id=self.value())
        return queryset

class TestTypeFilter(admin.SimpleListFilter):
    title = 'Test Type'
    parameter_name = 'test_type'

    def lookups(self, request, model_admin):
        return (
            ('regular', 'Regular Tests'),
            ('makeup', 'Makeup Tests'),
        )

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(test_type=self.value())
        return queryset

class CertificateFilter(admin.SimpleListFilter):
    title = 'Certificate Status'
    parameter_name = 'certificate_status'

    def lookups(self, request, model_admin):
        return (
            ('has_cert', 'Has Certificate'),
            ('no_cert', 'No Certificate'),
        )

    def queryset(self, request, queryset):
        if self.value() == 'has_cert':
            return queryset.exclude(certificate='')
        elif self.value() == 'no_cert':
            return queryset.filter(certificate='')
        return queryset

@admin.register(TestReview)
class TestReviewAdmin(admin.ModelAdmin):
    list_display = [
        'user', 'test_display', 'score_display', 'score_category', 'test_type', 
        'domains_status', 'certificate_status', 'is_active_status', 'duration_display', 'created_at'
    ]
    
    list_filter = [
        ScoreRangeFilter, UserGroupFilter, TestTypeFilter, CertificateFilter,
        'test_type', 'domains', 'test', 'makeup_test', 'created_at',
        ('user', admin.RelatedOnlyFieldListFilter),
    ]
    
    search_fields = [
        'user__username', 'user__first_name', 'user__last_name', 'user__email',
        'test__name', 'makeup_test__name', 'score', 'key'
    ]
    
    list_per_page = 50
    date_hierarchy = 'created_at'
    ordering = ['-created_at']
    
    readonly_fields = ['key', 'created_at', 'updated_at', 'certificate_preview', 'user_groups_display']
    
    fieldsets = (
        ('Test Information', {
            'fields': ('test', 'makeup_test', 'test_type', 'user', 'user_groups_display')
        }),
        ('Results', {
            'fields': ('score', 'domains', 'duration', 'key')
        }),
        ('Certificate', {
            'fields': ('certificate', 'certificate_preview'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'user', 'test', 'makeup_test'
        ).prefetch_related('user__groups')
    
    def test_display(self, obj):
        if obj.test:
            return format_html('<strong>{}</strong>', obj.test.name)
        elif obj.makeup_test:
            return format_html('<em>{}</em> (Makeup)', obj.makeup_test.name)
        return '-'
    test_display.short_description = 'Test'
    test_display.admin_order_field = 'test__name'
    
    def score_display(self, obj):
        if obj.score:
            color = self.get_score_color(obj.score)
            return format_html('<span style="color: {}; font-weight: bold;">{}</span>', color, obj.score)
        return '-'
    score_display.short_description = 'Score'
    score_display.admin_order_field = 'score'
    
    def get_score_color(self, score):
        if score >= 1400: return '#2e7d32'  # Dark green
        elif score >= 1200: return '#388e3c'  # Green
        elif score >= 1000: return '#689f38'  # Light green
        elif score >= 800: return '#f57c00'  # Orange
        elif score >= 600: return '#f44336'  # Red
        else: return '#d32f2f'  # Dark red
    
    def score_category(self, obj):
        if not obj.score:
            return '-'
        if obj.score >= 1400: return '🎯 Perfect'
        elif obj.score >= 1200: return '🌟 Excellent'
        elif obj.score >= 1000: return '👍 Very Good'
        elif obj.score >= 800: return '✅ Good'
        elif obj.score >= 600: return '⚠️ Average'
        else: return '🔻 Below Average'
    score_category.short_description = 'Performance'
    
    def domains_status(self, obj):
        if obj.domains:
            return format_html('<span style="color: #2e7d32;">✅ Complete</span>')
        else:
            return format_html('<span style="color: #f57c00;">⏳ Pending</span>')
    domains_status.short_description = 'Domains'
    
    def certificate_status(self, obj):
        if obj.certificate:
            return format_html('<span style="color: #2e7d32;">✅ Yes</span>')
        else:
            return format_html('<span style="color: #f44336;">❌ No</span>')
    certificate_status.short_description = 'Certificate'
    
    def is_active_status(self, obj):
        if obj.is_active():
            return format_html('<span style="color: #2e7d32;">✅ Active</span>')
        else:
            return format_html('<span style="color: #f44336;">❌ Expired</span>')
    is_active_status.short_description = 'Active'
    
    def duration_display(self, obj):
        if obj.duration:
            total_seconds = obj.duration.total_seconds()
            hours = int(total_seconds // 3600)
            return f'{hours}h' if hours > 0 else 'Active'
        return '-'
    duration_display.short_description = 'Duration'
    
    def certificate_preview(self, obj):
        if obj.certificate:
            return format_html('<textarea rows="3" cols="50" readonly>{}</textarea>', obj.certificate[:200] + '...' if len(obj.certificate) > 200 else obj.certificate)
        return 'No certificate generated'
    certificate_preview.short_description = 'Certificate Preview'
    
    def user_groups_display(self, obj):
        groups = obj.user.groups.all()
        if groups:
            group_badges = []
            for group in groups:
                color = {
                    'Admin': '#f44336',
                    'OFFLINE': '#2196f3',
                    'Testers': '#ff9800',
                }.get(group.name, '#9e9e9e')
                group_badges.append(f'<span style="background-color: {color}; color: white; padding: 2px 6px; border-radius: 3px; font-size: 11px;">{group.name}</span>')
            return format_html(' '.join(group_badges))
        return 'No groups'
    user_groups_display.short_description = 'User Groups'

    actions = ['regenerate_certificates', 'mark_domains_complete', 'extend_review_time']
    
    def regenerate_certificates(self, request, queryset):
        count = 0
        for review in queryset:
            if review.score:
                # Certificate regeneration logic would go here
                count += 1
        self.message_user(request, f'Certificates regenerated for {count} reviews.')
    regenerate_certificates.short_description = 'Regenerate certificates for selected reviews'
    
    def mark_domains_complete(self, request, queryset):
        count = queryset.update(domains=True)
        self.message_user(request, f'Marked domains complete for {count} reviews.')
    mark_domains_complete.short_description = 'Mark domains as complete'
    
    def extend_review_time(self, request, queryset):
        from datetime import timedelta
        count = 0
        for review in queryset:
            review.duration = timedelta(hours=48)  # Extend to 48 hours
            review.save()
            count += 1
        self.message_user(request, f'Extended review time for {count} reviews to 48 hours.')
    extend_review_time.short_description = 'Extend review time to 48 hours'

# Enhanced TestModule Admin
@admin.register(TestModule)
class TestModuleAdmin(admin.ModelAdmin):
    list_display = [
        'user', 'test_display', 'section', 'module', 'test_type', 
        'answers_count', 'created_display', 'user_groups_display'
    ]
    
    list_filter = [
        'section', 'module', 'test_type', 'test', 'makeup_test', 'created',
        UserGroupFilter,
        ('user', admin.RelatedOnlyFieldListFilter),
    ]
    
    search_fields = [
        'user__username', 'user__first_name', 'user__last_name',
        'test__name', 'makeup_test__name', 'section'
    ]
    
    list_per_page = 50
    date_hierarchy = 'created'
    ordering = ['-created']
    readonly_fields = ['created', 'updated_at', 'answers_preview']
    
    fieldsets = (
        ('Module Information', {
            'fields': ('test', 'makeup_test', 'test_type', 'user', 'section', 'module')
        }),
        ('Answers', {
            'fields': ('answers', 'answers_preview'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'user', 'test', 'makeup_test'
        ).prefetch_related('user__groups')
    
    def test_display(self, obj):
        if obj.test:
            return format_html('<strong>{}</strong>', obj.test.name)
        elif obj.makeup_test:
            return format_html('<em>{}</em> (Makeup)', obj.makeup_test.name)
        return '-'
    test_display.short_description = 'Test'
    
    def answers_count(self, obj):
        if obj.answers:
            try:
                answers_data = json.loads(obj.answers)
                count = len(answers_data.get('answers', []))
                return format_html('<strong>{}</strong> answers', count)
            except:
                return 'Invalid JSON'
        return '0 answers'
    answers_count.short_description = 'Answers'
    
    def created_display(self, obj):
        if obj.created:
            return obj.created.strftime('%Y-%m-%d %H:%M')
        return '-'
    created_display.short_description = 'Created'
    created_display.admin_order_field = 'created'
    
    def user_groups_display(self, obj):
        groups = obj.user.groups.all()
        if groups:
            return ', '.join([group.name for group in groups])
        return 'No groups'
    user_groups_display.short_description = 'User Groups'
    
    def answers_preview(self, obj):
        if obj.answers:
            try:
                answers_data = json.loads(obj.answers)
                preview = json.dumps(answers_data, indent=2)[:500]
                return format_html('<pre style="font-size: 11px;">{}</pre>', preview)
            except:
                return 'Invalid JSON format'
        return 'No answers recorded'
    answers_preview.short_description = 'Answers Preview'

# Enhanced TestStage Admin
@admin.register(TestStage)
class TestStageAdmin(admin.ModelAdmin):
    list_display = [
        'user', 'test_display', 'stage_display', 'test_type', 
        'retake_info', 'can_retake', 'created_at', 'user_groups_display'
    ]
    
    list_filter = [
        'stage', 'again', 'test_type', 'test', 'makeup_test',
        UserGroupFilter,
        ('user', admin.RelatedOnlyFieldListFilter),
        'created_at'
    ]
    
    search_fields = [
        'user__username', 'user__first_name', 'user__last_name',
        'test__name', 'makeup_test__name'
    ]
    
    list_per_page = 50
    ordering = ['-created_at']
    readonly_fields = ['created_at', 'updated_at', 'max_retakes_display']
    
    fieldsets = (
        ('Stage Information', {
            'fields': ('test', 'makeup_test', 'test_type', 'user', 'stage', 'again')
        }),
        ('Retake Information', {
            'fields': ('retake_count', 'max_retakes_display')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'user', 'test', 'makeup_test'
        ).prefetch_related('user__groups')
    
    def test_display(self, obj):
        if obj.test:
            return format_html('<strong>{}</strong>', obj.test.name)
        elif obj.makeup_test:
            return format_html('<em>{}</em> (Makeup)', obj.makeup_test.name)
        return '-'
    test_display.short_description = 'Test'
    
    def stage_display(self, obj):
        stage_names = {
            0: '🏁 Starting',
            1: '📚 English M1',
            2: '📚 English M2', 
            3: '🔢 Math M1',
            4: '🔢 Math M2',
            5: '✅ Complete'
        }
        return stage_names.get(obj.stage, f'Stage {obj.stage}')
    stage_display.short_description = 'Current Stage'
    
    def retake_info(self, obj):
        max_retakes = obj.get_max_retakes()
        return f'{obj.retake_count}/{max_retakes}'
    retake_info.short_description = 'Retakes Used'
    
    def can_retake(self, obj):
        if obj.retake_count < obj.get_max_retakes():
            return format_html('<span style="color: #2e7d32;">✅ Yes</span>')
        else:
            return format_html('<span style="color: #f44336;">❌ No</span>')
    can_retake.short_description = 'Can Retake'
    
    def user_groups_display(self, obj):
        groups = obj.user.groups.all()
        if groups:
            return ', '.join([group.name for group in groups])
        return 'No groups'
    user_groups_display.short_description = 'User Groups'
    
    def max_retakes_display(self, obj):
        return f'{obj.get_max_retakes()} (based on user groups)'
    max_retakes_display.short_description = 'Max Retakes Allowed'

    actions = ['reset_stage', 'allow_extra_retake']
    
    def reset_stage(self, request, queryset):
        count = 0
        for stage in queryset:
            if stage.resolve():
                count += 1
        self.message_user(request, f'Reset {count} test stages successfully.')
    reset_stage.short_description = 'Reset selected test stages'
    
    def allow_extra_retake(self, request, queryset):
        count = 0
        for stage in queryset:
            max_retakes = stage.get_max_retakes()
            if stage.retake_count >= max_retakes:
                # Allow one extra retake
                stage.retake_count = max_retakes - 1
                stage.save()
                count += 1
        self.message_user(request, f'Allowed extra retake for {count} test stages.')
    allow_extra_retake.short_description = 'Allow one extra retake'

# Lesson Management Group
LESSON_MANAGEMENT_GROUP = "Lesson Management"

class LessonInline(admin.TabularInline):
    model = Lesson
    extra = 1
    show_change_link = True

class LessonProgressInline(admin.TabularInline):
    model = LessonProgress
    extra = 0
    show_change_link = True

@admin.register(LessonPackage)
class LessonPackageAdmin(admin.ModelAdmin):
    list_display = ["name", "created_at", "updated_at"]
    search_fields = ["name"]
    inlines = [LessonInline]

@admin.register(Lesson)
class LessonAdmin(admin.ModelAdmin):
    list_display = ["name", "package", "order", "subject", "created_at", "updated_at"]
    list_filter = ["subject"]
    search_fields = ["name"]
    inlines = [LessonProgressInline]

@admin.register(LessonProgress)
class LessonProgressAdmin(admin.ModelAdmin):
    list_display = ["user", "lesson", "score", "completed", "created_at", "updated_at"]
    list_filter = ["completed"]
    search_fields = ["user__username", "lesson__name"]

# MakeupTest Admin Setup
class MakeupTestEnglishQuestionInline(admin.TabularInline):
    model = MakeupTestEnglishQuestion
    extra = 1
    fields = ('english_question', 'order')

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "english_question":
            kwargs["queryset"] = English_Question.objects.all().order_by('test__name', 'module', 'number')
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

class MakeupTestMathQuestionInline(admin.TabularInline):
    model = MakeupTestMathQuestion
    extra = 1
    fields = ('math_question', 'order')
    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "math_question":
            kwargs["queryset"] = Math_Question.objects.all().order_by('test__name', 'module', 'number')
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

@admin.register(MakeupTest)
class MakeupTestAdmin(admin.ModelAdmin):
    list_display = ('name', 'total_questions', 'created_at')
    list_filter = ('groups', 'created_at')
    search_fields = ('name', 'description')
    inlines = [MakeupTestEnglishQuestionInline, MakeupTestMathQuestionInline]
    filter_horizontal = ('groups',)

    def total_questions(self, obj):
        return obj.get_total_questions()
    total_questions.short_description = "Total Questions"

# SecretCode Admin Setup
@admin.register(SecretCode)
class SecretCodeAdmin(admin.ModelAdmin):
    list_display = ('code', 'group', 'test', 'created_at')
    list_filter = ('group', 'makeup_test','test')
    search_fields = ('code', 'group__name', 'makeup_test__name','test')
    fields = ('code', 'group', 'makeup_test','test')

    def save_model(self, request, obj, form, change):
        if not obj.code or len(obj.code) != 6 or not obj.code.isdigit():
            while True:
                code = ''.join(random.choices(string.digits, k=6))
                if not SecretCode.objects.filter(code=code).exists():
                    obj.code = code
                    break
        super().save_model(request, obj, form, change)


class VocabularyWordInline(admin.TabularInline):
    model = VocabularyWord
    extra = 1


@admin.register(VocabularyUnit)
class VocabularyUnitAdmin(admin.ModelAdmin):
    list_display = ('title', 'order', 'is_active', 'words_count')
    list_filter = ('is_active',)
    search_fields = ('title', 'description')
    ordering = ('order', 'id')
    inlines = [VocabularyWordInline]


@admin.register(VocabularyWord)
class VocabularyWordAdmin(admin.ModelAdmin):
    list_display = ('word', 'unit', 'is_active', 'created_at')
    list_filter = ('unit', 'is_active')
    search_fields = ('word', 'meaning', 'example', 'unit__title')
    ordering = ('unit', 'id')


@admin.register(VocabularyQuestion)
class VocabularyQuestionAdmin(admin.ModelAdmin):
    list_display = ('short_question', 'unit', 'correct_answer', 'is_active', 'created_at')
    list_filter = ('unit', 'is_active')
    search_fields = ('question', 'choice_a', 'choice_b', 'choice_c', 'choice_d', 'correct_answer', 'unit__title')
    ordering = ('unit', 'id')

    def short_question(self, obj):
        return obj.question[:70]
    short_question.short_description = 'Question'


class ClassroomJoinCodeInline(admin.StackedInline):
    model = ClassroomJoinCode
    extra = 0
    can_delete = False


class ClassroomMembershipInline(admin.TabularInline):
    model = ClassroomMembership
    extra = 0
    fields = ('user', 'role', 'status', 'requested_at', 'approved_at')
    readonly_fields = ('requested_at', 'approved_at')


@admin.register(Classroom)
class ClassroomAdmin(admin.ModelAdmin):
    list_display = ('name', 'teacher', 'is_active', 'created_at')
    list_filter = ('is_active', 'created_at')
    search_fields = ('name', 'teacherusername', 'teacherfirst_name', 'teacher__last_name')
    inlines = [ClassroomJoinCodeInline, ClassroomMembershipInline]


@admin.register(ClassroomJoinCode)
class ClassroomJoinCodeAdmin(admin.ModelAdmin):
    list_display = ('classroom', 'code', 'is_active', 'expires_at', 'created_at')
    list_filter = ('is_active', 'created_at', 'expires_at')
    search_fields = ('classroom__name', 'code')


@admin.register(ClassroomMembership)
class ClassroomMembershipAdmin(admin.ModelAdmin):
    list_display = ('user', 'classroom', 'role', 'status', 'requested_at', 'approved_at')
    list_filter = ('role', 'status', 'requested_at')
    search_fields = ('userusername', 'classroomname')


@admin.register(StudentSectionAccess)
class StudentSectionAccessAdmin(admin.ModelAdmin):
    list_display = ('membership', 'section', 'has_access', 'updated_at')
    list_filter = ('section', 'has_access')
    search_fields = ('membershipuserusername', 'membershipclassroomname')


@admin.register(StudentProgress)
class StudentProgressAdmin(admin.ModelAdmin):
    list_display = (
        'student',
        'classroom',
        'section',
        'completion_percent',
        'completed_items',
        'total_items',
        'activity_count',
        'last_activity_at',
    )
    list_filter = ('section', 'classroom')
    search_fields = ('studentusername', 'classroomname')


@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    list_display = ('sender', 'classroom', 'is_deleted', 'created_at')
    list_filter = ('is_deleted', 'created_at', 'classroom')
    search_fields = ('senderusername', 'classroomname', 'message')

@admin.register(GlobalEvent)
class GlobalEventAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "test",
        "slug",
        "status",
        "is_public",
        "show_score_immediately",
        "show_leaderboard",
        "start_at",
        "end_at",
    )
    search_fields = ("title", "slug", "test__title")
    list_filter = ("status", "is_public", "show_score_immediately", "show_leaderboard")
    autocomplete_fields = ("test",)
    list_editable = ("show_score_immediately", "show_leaderboard", "status", "is_public")


@admin.register(GuestParticipant)
class GuestParticipantAdmin(admin.ModelAdmin):
    list_display = ("full_name", "display_name", "created_at")
    search_fields = ("full_name", "display_name")


@admin.register(GlobalEventAttempt)
class GlobalEventAttemptAdmin(admin.ModelAdmin):
    list_display = ("event", "guest", "status", "score", "started_at", "submitted_at")
    list_filter = ("status", "event")
    search_fields = ("guest__full_name", "guest__display_name", "event__title")


@admin.register(GlobalEventAnswer)
class GlobalEventAnswerAdmin(admin.ModelAdmin):
    list_display = ("attempt", "section", "module", "question_id", "selected_answer", "is_correct", "answered_at")
    list_filter = ("section", "module", "is_correct")
    search_fields = (
        "attempt__guest__full_name",
        "attempt__guest__display_name",
        "attempt__event__title",
        "selected_answer",
    )