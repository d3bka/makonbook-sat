from django.db import models
from django.contrib.auth.models import User, Group
from datetime import timedelta
import datetime
import random
import string
import uuid
import secrets
import urllib.parse
import json
import time
from django.utils.timezone import now
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db.models.signals import pre_delete
from django.dispatch import receiver
from .storages import PublicStorage, PrivateStorage
from django.utils import timezone
from django.core.validators import MinValueValidator, MaxValueValidator
from django.core.exceptions import ValidationError

# Abstract base model for common fields
class BaseModel(models.Model):
    """Abstract model to include created_at and updated_at for all models."""
    created_at = models.DateTimeField(auto_now_add=True, null=True)
    updated_at = models.DateTimeField(auto_now=True, null=True)

    class Meta:
        abstract = True

# Video model for lessons and test explanations
class BaseVideo(models.Model):
    """
    A base video model for handling both lesson videos and test-solved videos.

    Features:
    - Supports external uploads (via pre-signed URLs) rather than admin-panel uploads.
    - Can be attached to various content types (e.g., Lesson, TestSolved) via a generic relation.
    - Stores the raw video file (e.g., MP4) and the processed HLS URL.
    - Tracks conversion status and includes metadata like duration and resolution.
    - Provides helper methods for generating secure access tokens and signed URLs.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=255)
    
    VIDEO_TYPE_CHOICES = [
        ('lesson', 'Lesson Video'),
        ('test_solved', 'Test Solved Video'),
    ]
    video_type = models.CharField(max_length=20, choices=VIDEO_TYPE_CHOICES)
    
    # Generic relation to attach this video to any object (e.g., Lesson or TestSolved)
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, null=True, blank=True)
    object_id = models.PositiveIntegerField(null=True, blank=True)
    attached_object = GenericForeignKey('content_type', 'object_id')
    
    video_file = models.FileField(
        upload_to='videos/raw/',
        storage=PrivateStorage(),
        blank=True,
        null=True,
        help_text="Uploaded externally; not via the admin panel."
    )
    
    hls_url = models.URLField(
        blank=True,
        null=True,
        help_text="URL to the HLS manifest (e.g., output.m3u8) after processing."
    )
    
    CONVERSION_STATUSES = [
        ('pending', 'Pending'),
        ('converting', 'Converting'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]
    conversion_status = models.CharField(
        max_length=20,
        choices=CONVERSION_STATUSES,
        default='pending'
    )
    
    description = models.TextField(blank=True)
    duration = models.DurationField(blank=True, null=True)
    resolution = models.CharField(max_length=50, blank=True, null=True)
    access_token = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="Token used for generating secure access to the video."
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Video"
        verbose_name_plural = "Videos"
    
    def __str__(self):
        return self.title

    def generate_access_token(self):
        """Generate a secure access token for signing URLs."""
        self.access_token = secrets.token_urlsafe(32)
        self.save(update_fields=['access_token'])
        return self.access_token

    def get_signed_hls_url(self, expiration_seconds=3600):
        """
        Generate a signed URL for secure access to the HLS manifest.
        Valid for a limited period (default: 1 hour).
        """
        if not self.hls_url:
            return None
        
        if not self.access_token:
            self.generate_access_token()
        
        expires = int(time.time()) + expiration_seconds
        query_params = {'token': self.access_token, 'expires': expires}
        signed_url = f"{self.hls_url}?{urllib.parse.urlencode(query_params)}"
        return signed_url

# Question categorization
class QuestionDomain(BaseModel):
    name = models.CharField(max_length=100)

    def __str__(self):
        return self.name

class QuestionType(BaseModel):
    name = models.CharField(max_length=100)
    domain = models.ForeignKey(QuestionDomain, on_delete=models.CASCADE)

    def __str__(self):
        return self.name

# User punishment tracking
class Punishment(BaseModel):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    name = models.TextField('Name of the punishment', null=True)
    created = models.DateTimeField('When happened', auto_now=True)

# Test model
class Test(BaseModel):
    name = models.CharField(max_length=400, unique=True, primary_key=True)
    created = models.DateTimeField(auto_now=True)
    groups = models.ManyToManyField(Group, related_name='tests')
    icon = models.ImageField(
        'Icon',
        upload_to='sat/test_icons',
        storage=PublicStorage(),
        null=True,
        blank=True,
        help_text='Upload an icon or photo for this test.'
    )

    def get_number(self):
        return int(self.name)

    def __str__(self):
        return self.name

# Choices for modules
modules = [('module_1', "Module 1"), ('module_2', "Module 2")]

# English questions
class English_Question(BaseModel):
    RESPONSE_TYPE_CHOICES = [
        ("multiple_choice", "Multiple choice"),
        ("open_text", "Open text (deterministic matching)"),
    ]

    test = models.ForeignKey(Test, on_delete=models.SET_NULL, null=True)
    module = models.CharField(max_length=8, choices=modules, null=True)
    domain = models.ForeignKey(QuestionDomain, on_delete=models.SET_NULL, null=True, blank=True)
    type = models.ForeignKey(QuestionType, on_delete=models.SET_NULL, blank=True, null=True)
    image = models.ImageField(
        'Image',
        upload_to='sat/question_images',
        storage=PublicStorage(),
        null=True,
        blank=True
    )
    number = models.IntegerField('Question Number', null=True)
    passage = models.TextField('Passage', blank=True, null=True)
    question = models.TextField('Question', blank=True, null=True)
    a = models.TextField('Choice A', blank=True, null=True)
    b = models.TextField('Choice B', blank=True, null=True)
    c = models.TextField('Choice C', blank=True, null=True)
    d = models.TextField('Choice D', blank=True, null=True)
    graph = models.BooleanField('Is there Graph or Table', default=False)
    response_type = models.CharField(
        max_length=24,
        choices=RESPONSE_TYPE_CHOICES,
        default="multiple_choice",
    )
    answer = models.CharField('Answer', null=True, blank=True, max_length=400)
    accepted_answers = models.TextField(
        blank=True,
        help_text="One accepted full answer per line. Matching ignores case, repeated spaces, and final punctuation.",
    )
    answer_patterns = models.TextField(
        blank=True,
        help_text="Optional regular expressions, one per line. Each pattern must match the entire normalized response.",
    )
    explained = models.TextField('Explanation', blank=True, null=True)

    @property
    def is_open_text(self):
        return self.response_type == "open_text"

    def graph_url(self):
        if self.graph and self.image:
            return self.image.url
        return ''

    def __str__(self):
        return f'{self.test}>module-{self.module}> #{self.number}'

# Math questions
class Math_Question(BaseModel):
    test = models.ForeignKey(Test, on_delete=models.SET_NULL, null=True)
    module = models.CharField(max_length=8, choices=modules, null=True)
    domain = models.ForeignKey(QuestionDomain, on_delete=models.SET_NULL, null=True, blank=True)
    type = models.ForeignKey(QuestionType, on_delete=models.SET_NULL, blank=True, null=True)
    image = models.ImageField('Image', upload_to='sat/question_images', storage=PublicStorage(), null=True, blank=True)
    number = models.IntegerField('Question Number', null=True)
    passage = models.TextField('Passage', blank=True, null=True)
    question = models.TextField('Question', blank=True, null=True)
    a = models.TextField('Choice A', blank=True, null=True)
    b = models.TextField('Choice B', blank=True, null=True)
    c = models.TextField('Choice C', blank=True, null=True)
    d = models.TextField('Choice D', blank=True, null=True)
    image_a = models.ImageField('Image A', upload_to='sat/choice_images', storage=PublicStorage(), null=True, blank=True)
    image_b = models.ImageField('Image B', upload_to='sat/choice_images', storage=PublicStorage(), null=True, blank=True)
    image_c = models.ImageField('Image C', upload_to='sat/choice_images', storage=PublicStorage(), null=True, blank=True)
    image_d = models.ImageField('Image D', upload_to='sat/choice_images', storage=PublicStorage(), null=True, blank=True)
    graph = models.BooleanField('Is there Graph or Table', default=False)
    choice_graph = models.BooleanField('Is there Graph or Table in choices', default=False)
    written = models.BooleanField("Is it write type question", default=False)
    answer = models.CharField('Answer', null=True, blank=True, max_length=400)
    explained = models.TextField('Explanation', blank=True, null=True)
    img_explain = models.ImageField('Image Explanation', upload_to='sat/question_images', storage=PublicStorage(), null=True, blank=True)

    def get_a(self):
        if self.choice_graph and self.image_a:
            return f"IMAGE:{self.image_a.url}"
        return self.a
    
    def get_b(self):
        if self.choice_graph and self.image_b:
            return f"IMAGE:{self.image_b.url}"
        return self.b
    
    def get_c(self):
        if self.choice_graph and self.image_c:
            return f"IMAGE:{self.image_c.url}"
        return self.c
    
    def get_d(self):
        if self.choice_graph and self.image_d:
            return f"IMAGE:{self.image_d.url}"
        return self.d

    def get_graph(self):
        if self.graph and self.image:
            return self.image.url
        return ''

    def get_exp(self):
        if self.img_explain:
            return f'<img style="max-width: 400px" src="{self.img_explain.url}"></img>'
        return self.explained

    def __str__(self):
        return f'{self.test}>module-{self.module}> #{self.number}'

# models.py
class MakeupTestEnglishQuestion(models.Model):
    makeup_test = models.ForeignKey('MakeupTest', on_delete=models.CASCADE)
    english_question = models.ForeignKey('English_Question', on_delete=models.CASCADE)
    order = models.PositiveIntegerField(default=0, help_text="Order within this makeup test")

    class Meta:
        unique_together = ('makeup_test', 'english_question')
        ordering = ['order']

    def __str__(self):
        return f"{self.makeup_test.name} - {self.english_question} (Order: {self.order})"

class MakeupTestMathQuestion(models.Model):
    makeup_test = models.ForeignKey('MakeupTest', on_delete=models.CASCADE)
    math_question = models.ForeignKey('Math_Question', on_delete=models.CASCADE)
    order = models.PositiveIntegerField(default=0, help_text="Order within this makeup test")

    class Meta:
        unique_together = ('makeup_test', 'math_question')
        ordering = ['order']

    def __str__(self):
        return f"{self.makeup_test.name} - {self.math_question} (Order: {self.order})"

class MakeupTest(models.Model):
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    groups = models.ManyToManyField('auth.Group', blank=True)
    english_questions = models.ManyToManyField(
        'English_Question',
        blank=True,
        related_name="makeup_tests_english",
        through='MakeupTestEnglishQuestion'
    )
    math_questions = models.ManyToManyField(
        'Math_Question',
        blank=True,
        related_name="makeup_tests_math",
        through='MakeupTestMathQuestion'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def get_total_questions(self):
        return self.english_questions.count() + self.math_questions.count()
    
    def get_module_questions(self, section, module=None):
        """
        Returns a queryset of questions for the given section ('english' or 'math') and optional module.
        Orders questions based on the 'order' field in the through model.
        """
        if section == 'english':
            queryset = English_Question.objects.filter(
                makeup_tests_english=self
            ).order_by('makeuptestenglishquestion__order')
            if module:
                queryset = queryset.filter(module=module)  # Filter by module if provided
            return queryset
        elif section == 'math':
            queryset = Math_Question.objects.filter(
                makeup_tests_math=self
            ).order_by('makeuptestmathquestion__order')
            if module:
                queryset = queryset.filter(module=module)  # Filter by module if provided
            return queryset
        return None
    def __str__(self):
        return self.name

# Test module for tracking user answers
class TestModule(BaseModel):
    test = models.ForeignKey(Test, on_delete=models.SET_NULL, null=True, blank=True, related_name="modules")
    makeup_test = models.ForeignKey(MakeupTest, on_delete=models.SET_NULL, null=True, blank=True, related_name="test_modules")
    user = models.ForeignKey(User, null=True, on_delete=models.CASCADE)
    classroom = models.ForeignKey('Classroom', on_delete=models.SET_NULL, null=True, blank=True, related_name='test_modules')

    section = models.CharField(max_length=8)
    module = models.CharField(
        choices=[('m1', 'Module 1'), ('m2', 'Module 2')],
        max_length=8,
        blank=True,
        null=True
    )

    answers = models.TextField(blank=True, null=True)

    created = models.DateTimeField(auto_now_add=True, null=True)

    TEST_TYPE_CHOICES = [
        ('regular', 'Regular Test'),
        ('makeup', 'Makeup Test'),
    ]
    test_type = models.CharField(
        max_length=20,
        choices=TEST_TYPE_CHOICES,
        default='regular'
    )

    attempt_id = models.UUIDField(default=uuid.uuid4, editable=False)

    def find_answer(self, question_id):
        previous, now, future = '', '', ''
        target_id = str(question_id)

        try:
            payload = json.loads(self.answers or '{"answers": []}')
            answers = payload.get('answers', [])
        except Exception:
            return previous, now, future

        for item in answers:
            item_id = str(item.get('questionID', ''))

            if now:
                future = item_id
                break

            if item_id == target_id:
                raw_answer = item.get('answer')
                now = '' if raw_answer is None else str(raw_answer)
            else:
                previous = item_id

        return previous, now, future

    def __str__(self):
        return f'{self.user}>{self.test}_{self.section}_{self.module}_{self.attempt_id}'

    class Meta:
        ordering = ['created']
        indexes = [
            models.Index(fields=['user', 'test', 'attempt_id', 'created'], name='sat_tm_u_t_att_cr'),
            models.Index(fields=['user', 'test', 'section', 'module', 'created'], name='sat_tm_u_t_sec_mod'),
        ]

class TestModuleDraft(BaseModel):
    """Server-side resumable state for an in-progress SAT module.

    ``TestModule`` remains the immutable submitted module. This model stores only
    drafts so a refresh, browser crash, or device change does not erase answers.
    The row is deleted as soon as the module is submitted successfully.
    """
    test = models.ForeignKey(Test, on_delete=models.CASCADE, related_name="module_drafts")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="sat_module_drafts")
    classroom = models.ForeignKey(
        'Classroom',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='test_module_drafts',
    )
    attempt_id = models.UUIDField(editable=False)
    section = models.CharField(max_length=8)
    module = models.CharField(max_length=8)
    answers = models.JSONField(default=list, blank=True)
    time_spent = models.JSONField(default=list, blank=True)
    eliminated_choices = models.JSONField(default=list, blank=True)
    marked_for_review = models.JSONField(default=list, blank=True)
    current_question_index = models.PositiveIntegerField(default=0)
    deadline_at = models.DateTimeField()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'test', 'attempt_id', 'section', 'module'],
                name='sat_unique_module_draft',
            ),
        ]
        indexes = [
            models.Index(
                fields=['user', 'test', 'attempt_id'],
                name='sat_tmd_u_t_att',
            ),
            models.Index(
                fields=['deadline_at'],
                name='sat_tmd_deadline',
            ),
        ]

    def __str__(self):
        return f'{self.user}>{self.test}_{self.section}_{self.module}_{self.attempt_id}'


class MakeupTestModuleDraft(BaseModel):
    """Server-side resumable state for an in-progress Makeup module."""
    makeup_test = models.ForeignKey(
        MakeupTest,
        on_delete=models.CASCADE,
        related_name="module_drafts",
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="makeup_module_drafts",
    )
    attempt_id = models.UUIDField(editable=False)
    section = models.CharField(max_length=8)
    module = models.CharField(max_length=8)
    answers = models.JSONField(default=list, blank=True)
    time_spent = models.JSONField(default=list, blank=True)
    eliminated_choices = models.JSONField(default=list, blank=True)
    marked_for_review = models.JSONField(default=list, blank=True)
    current_question_index = models.PositiveIntegerField(default=0)
    deadline_at = models.DateTimeField()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'makeup_test', 'attempt_id', 'section', 'module'],
                name='sat_unique_makeup_module_draft',
            ),
        ]
        indexes = [
            models.Index(
                fields=['user', 'makeup_test', 'attempt_id'],
                name='sat_mtd_u_t_att',
            ),
            models.Index(fields=['deadline_at'], name='sat_mtd_deadline'),
        ]

    def __str__(self):
        return f'{self.user}>{self.makeup_test}_{self.section}_{self.module}_{self.attempt_id}'


# Test review and scoring
class TestReview(BaseModel):
    test = models.ForeignKey(Test, on_delete=models.SET_NULL, null=True, blank=True, related_name="test_reviews")
    makeup_test = models.ForeignKey(MakeupTest, on_delete=models.SET_NULL, null=True, blank=True, related_name="makeup_test_reviews")
    user = models.ForeignKey(User, null=True, on_delete=models.CASCADE)
    classroom = models.ForeignKey('Classroom', on_delete=models.SET_NULL, null=True, blank=True, related_name='test_reviews')
    key = models.CharField(max_length=100, blank=True, unique=True)
    attempt_id = models.UUIDField(default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    duration = models.DurationField(default=timedelta(hours=24))
    score = models.IntegerField(default=None, null=True, blank=True)
    certificate = models.TextField(blank=True)
    domains = models.BooleanField(default=False)
    
    TEST_TYPE_CHOICES = [
        ('regular', 'Regular Test'),
        ('makeup', 'Makeup Test'),
    ]
    test_type = models.CharField(max_length=20, choices=TEST_TYPE_CHOICES, default='regular')

    def check_and_update_domains(self):
        if not self.domains:
            english_questions = English_Question.objects.filter(test=self.test)
            math_questions = Math_Question.objects.filter(test=self.test)
            for question in english_questions:
                if question.domain is None:
                    return question.id
            for question in math_questions:
                if question.domain is None:
                    return question.id
            self.domains = True
            self.save()
        return True

    def is_active(self):
        """Review answers do not expire.

        Keep the method for backwards compatibility with existing views/admin
        that call review.is_active(), but do not enforce a time window anymore.
        """
        return True

    def update_key(self):
        self.key = ''.join(random.choices(string.ascii_letters, k=100))
        self.save()

    def __str__(self):
        return f"{self.user.username} - {self.test} - {self.score}"

    class Meta:
        indexes = [
            models.Index(fields=['user', 'test', 'attempt_id', 'created_at'], name='sat_tr_u_t_att_cr'),
            models.Index(fields=['user', 'test', 'created_at'], name='sat_tr_u_t_cr'),
        ]

# Test stages for user progress
class TestStage(BaseModel):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    test = models.ForeignKey(Test, on_delete=models.SET_NULL, null=True, blank=True, related_name="test_stages")
    makeup_test = models.ForeignKey(MakeupTest, on_delete=models.SET_NULL, null=True, blank=True, related_name="makeup_test_stages")
    classroom = models.ForeignKey('Classroom', on_delete=models.SET_NULL, null=True, blank=True, related_name='test_stages')
    stage = models.IntegerField()
    again = models.BooleanField(default=True)
    retake_count = models.IntegerField(default=0, help_text="Number of retakes used by this user")
    attempt_id = models.UUIDField(default=uuid.uuid4, editable=False)

    TEST_TYPE_CHOICES = [
        ('regular', 'Regular Test'),
        ('makeup', 'Makeup Test'),
    ]
    test_type = models.CharField(max_length=20, choices=TEST_TYPE_CHOICES, default='regular')

    def get_max_retakes(self):
        # unlimited
        return None

    def _latest_completed_attempt_id(self):
        latest_review = TestReview.objects.filter(
            test=self.test,
            user=self.user,
            classroom_id=self.classroom_id,
            score__isnull=False,
            attempt_id__isnull=False,
        ).order_by('-created_at').first()

        return latest_review.attempt_id if latest_review else None

    def _copy_modules_to_attempt(self, *, from_attempt_id, to_attempt_id, exclude_section=None):
        if not from_attempt_id:
            return

        modules = TestModule.objects.filter(
            test=self.test,
            user=self.user,
            classroom_id=self.classroom_id,
            attempt_id=from_attempt_id,
            test_type=self.test_type,
        )

        if exclude_section:
            modules = modules.exclude(section=exclude_section)

        for module in modules:
            TestModule.objects.create(
                test=module.test,
                makeup_test=module.makeup_test,
                user=module.user,
                classroom=module.classroom,
                section=module.section,
                module=module.module,
                answers=module.answers,
                test_type=module.test_type,
                attempt_id=to_attempt_id,
            )

    def invalidate_review(self):
        """Deprecated: old reviews must stay immutable after retakes."""
        return

    class Meta:
        indexes = [
            models.Index(fields=['user', 'test', 'created_at'], name='sat_ts_u_t_cr'),
            models.Index(fields=['user', 'test', 'attempt_id'], name='sat_ts_u_t_att'),
        ]

    def delete_modules(self, section=None):
        """Deprecated: retakes create new attempts instead of deleting history."""
        return

    def resolve(self):
        """Start a new full-test attempt without deleting old modules/reviews."""
        max_retakes = self.get_max_retakes()

        if max_retakes is not None and self.retake_count >= max_retakes:
            self.again = False
            self.save(update_fields=['again'])
            return False

        previous_attempt_id = self.attempt_id
        self.stage = 1
        self.retake_count += 1
        self.attempt_id = uuid.uuid4()
        self.save(update_fields=['stage', 'retake_count', 'attempt_id', 'updated_at'])
        TestModuleDraft.objects.filter(
            user=self.user,
            test=self.test,
            classroom_id=self.classroom_id,
            attempt_id=previous_attempt_id,
        ).delete()
        return True

    def resolve_section(self, section):
        """
        Start a new attempt from the requested section.
        Old attempts are preserved. Modules from other sections are copied into the
        new attempt so results/certificates stay tied to one attempt_id.
        """
        max_retakes = self.get_max_retakes()

        if max_retakes is not None and self.retake_count >= max_retakes:
            self.again = False
            self.save(update_fields=['again'])
            return False

        section = str(section or '').strip().lower()
        module_order = {'module_1': 0, 'module_2': 1, 'm1': 0, 'm2': 1}
        sequence = []
        english_modules = English_Question.objects.filter(test=self.test).values_list('module', flat=True).distinct()
        math_modules = Math_Question.objects.filter(test=self.test).values_list('module', flat=True).distinct()

        for db_module in sorted(english_modules, key=lambda item: module_order.get(item, 99)):
            module = 'm1' if db_module == 'module_1' else 'm2' if db_module == 'module_2' else db_module
            sequence.append(('english', module))
        for db_module in sorted(math_modules, key=lambda item: module_order.get(item, 99)):
            module = 'm1' if db_module == 'module_1' else 'm2' if db_module == 'module_2' else db_module
            sequence.append(('math', module))

        start_stage = None
        for index, (seq_section, _seq_module) in enumerate(sequence, start=1):
            if seq_section == section:
                start_stage = index
                break

        if start_stage is None:
            return False

        previous_attempt_id = self._latest_completed_attempt_id()
        if not previous_attempt_id:
            return False

        new_attempt_id = uuid.uuid4()
        self._copy_modules_to_attempt(
            from_attempt_id=previous_attempt_id,
            to_attempt_id=new_attempt_id,
            exclude_section=section,
        )

        stale_attempt_id = self.attempt_id
        self.stage = start_stage
        self.retake_count += 1
        self.attempt_id = new_attempt_id
        self.save(update_fields=['stage', 'retake_count', 'attempt_id', 'updated_at'])
        TestModuleDraft.objects.filter(
            user=self.user,
            test=self.test,
            classroom_id=self.classroom_id,
            attempt_id=stale_attempt_id,
        ).delete()
        return True

    def get_retakes_remaining(self):
        # unlimited
        return None

# Lesson packages and lessons
class LessonPackage(BaseModel):
    name = models.CharField(max_length=255, unique=True)
    image = models.ImageField(upload_to='lesson_packages/', null=True, blank=True)
    description = models.TextField()

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Lesson Package"
        verbose_name_plural = "Lesson Packages"

class Lesson(BaseModel):
    ENGLISH = "English"
    MATH = "Math"
    BOTH = "Both"
    SUBJECT_CHOICES = [
        (ENGLISH, "English"),
        (MATH, "Math"),
        (BOTH, "Both"),
    ]

    package = models.ForeignKey(LessonPackage, on_delete=models.CASCADE, related_name="lessons")
    order = models.PositiveIntegerField()
    name = models.CharField(max_length=255)
    subject = models.CharField(max_length=10, choices=SUBJECT_CHOICES, default=BOTH)
    question_type = models.ForeignKey('QuestionType', on_delete=models.SET_NULL, null=True, blank=True)

    def get_random_questions(self):
        """Select 15 random questions from the given question type."""
        if not self.question_type:
            return []
        if self.subject == self.ENGLISH:
            questions = English_Question.objects.filter(type=self.question_type)
        elif self.subject == self.MATH:
            questions = Math_Question.objects.filter(type=self.question_type)
        else:
            return []
        return random.sample(list(questions), min(15, questions.count()))

    def __str__(self):
        return f"{self.package.name} - {self.name} (Order {self.order}) - {self.subject}"

    class Meta:
        verbose_name = "Lesson"
        verbose_name_plural = "Lessons"

# Lesson progress tracking
class LessonProgress(BaseModel):
    """Tracks user progress for unlocking lessons."""
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    lesson = models.ForeignKey(Lesson, on_delete=models.CASCADE)
    videos_watched = models.BooleanField(default=False)
    score = models.PositiveIntegerField(default=0)
    completed = models.BooleanField(default=False)

    def check_completion(self):
        """Unlock next lesson if criteria are met (12/15 & watched all videos)."""
        videos_required = self.lesson.videos.exists()
        if self.score >= 12 and (not videos_required or self.videos_watched):
            self.completed = True
            self.save()

    def __str__(self):
        return f"{self.user.username} - {self.lesson.name} - Score: {self.score} - {'Completed' if self.completed else 'Locked'}"

    class Meta:
        verbose_name = "Lesson Progress"
        verbose_name_plural = "Lesson Progresses"

# Purchased lesson packages
class PurchasedLessonPackage(BaseModel):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="purchased_packages")
    package = models.ForeignKey(LessonPackage, on_delete=models.CASCADE, related_name="purchases")
    purchased_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'package')

    def __str__(self):
        return f"{self.user.username} - {self.package.name}"

# Secret code for group and test access
class SecretCode(BaseModel):
    """
    A model to store secret codes that grant group access and optionally link to a makeup test.
    """
    code = models.CharField(
        max_length=6,
        unique=True,
        help_text="6-digit secret code (e.g., '123456')"
    )
    group = models.ForeignKey(
        'auth.Group',
        on_delete=models.CASCADE,
        related_name="secret_codes",
        help_text="Group to add the user to when the code is entered"
    )
    makeup_test = models.ForeignKey(
        'MakeupTest',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="secret_codes",
        help_text="Optional: Makeup test to start after entering the code"
    )
    test = models.ForeignKey('Test', on_delete=models.SET_NULL, null=True, blank=True, related_name='secret_codes')  # Add test field
    
    def __str__(self):
        return f"{self.code} - {self.group.name}"

    def save(self, *args, **kwargs):
        """Generate a random 6-digit code if not provided."""
        if not self.code:
            while True:
                code = ''.join(random.choices(string.digits, k=6))
                if not SecretCode.objects.filter(code=code).exists():
                    self.code = code
                    break
        super().save(*args, **kwargs)

    class Meta:
        verbose_name = "Secret Code"
        verbose_name_plural = "Secret Codes"

# Mock model for bundled test+group+user creation
class Mock(BaseModel):
    name = models.CharField(max_length=255, unique=True)
    test = models.ForeignKey(Test, on_delete=models.SET_NULL, null=True, related_name='mocks')
    group = models.ForeignKey('auth.Group', on_delete=models.SET_NULL, null=True, related_name='mocks')
    secret_code = models.ForeignKey(SecretCode, on_delete=models.SET_NULL, null=True, blank=True, related_name='mocks')
    mode = models.CharField(max_length=20, choices=[('secret_code', 'Secret Code'), ('direct', 'Direct')])
    user_count = models.PositiveIntegerField()
    credentials = models.TextField(blank=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_mocks')

    def __str__(self):
        return self.name

# Signal to clean up related objects when TestStage is deleted
@receiver(pre_delete, sender=TestStage)
def delete_related_objects(sender, instance, **kwargs):
    # Old versions tried to call instance.delete_related(), but TestStage has no
    # such method in the current model. Keep this receiver safe so deleting a
    # stage from admin/scripts does not crash.
    cleanup = getattr(instance, "delete_related", None)
    if callable(cleanup):
        cleanup()

class VocabularyUnit(models.Model):
    title = models.CharField(max_length=200, unique=True)
    description = models.TextField(blank=True, null=True)
    order = models.PositiveIntegerField(default=1)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['order', 'id']

    def __str__(self):
        return self.title

    @property
    def words_count(self):
        return self.words.filter(is_active=True).count()


class VocabularyWord(models.Model):
    unit = models.ForeignKey(
        VocabularyUnit,
        on_delete=models.CASCADE,
        related_name='words'
    )
    word = models.CharField(max_length=255)
    meaning = models.TextField()
    example = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['id']
        unique_together = ('unit', 'word')

    def __str__(self):
        return f"{self.unit.title} - {self.word}"


class VocabularyQuestion(models.Model):
    unit = models.ForeignKey(
        VocabularyUnit,
        on_delete=models.CASCADE,
        related_name='questions'
    )
    question = models.TextField()
    choice_a = models.CharField(max_length=255)
    choice_b = models.CharField(max_length=255)
    choice_c = models.CharField(max_length=255)
    choice_d = models.CharField(max_length=255)
    correct_answer = models.CharField(max_length=255)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['id']

    def __str__(self):
        return f"{self.unit.title} - {self.question[:60]}"

    def get_choices(self):
        return [
            self.choice_a,
            self.choice_b,
            self.choice_c,
            self.choice_d,
        ]


class VocabularyWordProgress(models.Model):
    STATUS_NEW = 'new'
    STATUS_LEARNING = 'learning'
    STATUS_MASTERED = 'mastered'
    STATUS_CHOICES = (
        (STATUS_NEW, 'New'),
        (STATUS_LEARNING, 'Learning'),
        (STATUS_MASTERED, 'Mastered'),
    )

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='vocabulary_word_progress',
    )
    classroom = models.ForeignKey(
        'Classroom',
        on_delete=models.CASCADE,
        related_name='vocabulary_word_progress',
        null=True,
        blank=True,
    )
    word = models.ForeignKey(
        VocabularyWord,
        on_delete=models.CASCADE,
        related_name='student_progress',
    )
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_NEW)
    times_seen = models.PositiveIntegerField(default=0)
    correct_count = models.PositiveIntegerField(default=0)
    incorrect_count = models.PositiveIntegerField(default=0)
    consecutive_correct = models.PositiveIntegerField(default=0)
    last_reviewed_at = models.DateTimeField(blank=True, null=True)
    mastered_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['word__unit__order', 'word__id']
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'classroom', 'word'],
                name='unique_vocab_progress_scope',
            ),
        ]
        indexes = [
            models.Index(fields=['user', 'classroom', 'status'], name='vocab_prog_scope_status'),
            models.Index(fields=['classroom', 'last_reviewed_at'], name='vocab_prog_class_last'),
        ]

    @property
    def attempts_count(self):
        return self.correct_count + self.incorrect_count

    @property
    def accuracy_percent(self):
        total = self.attempts_count
        return round((self.correct_count / total) * 100, 1) if total else 0

    def __str__(self):
        scope = self.classroom.name if self.classroom_id else 'Global'
        return f"{self.user.username} · {scope} · {self.word.word} · {self.status}"


class VocabularyQuizAttempt(models.Model):
    MODE_WORD_TO_MEANING = 'word_to_meaning'
    MODE_MEANING_TO_WORD = 'meaning_to_word'
    MODE_MIXED = 'mixed'
    MODE_CHOICES = (
        (MODE_WORD_TO_MEANING, 'Word to meaning'),
        (MODE_MEANING_TO_WORD, 'Meaning to word'),
        (MODE_MIXED, 'Mixed'),
    )

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='vocabulary_quiz_attempts',
    )
    classroom = models.ForeignKey(
        'Classroom',
        on_delete=models.CASCADE,
        related_name='vocabulary_quiz_attempts',
        null=True,
        blank=True,
    )
    mode = models.CharField(max_length=24, choices=MODE_CHOICES, default=MODE_MIXED)
    selected_units = models.JSONField(default=list, blank=True)
    score = models.PositiveIntegerField(default=0)
    total_questions = models.PositiveIntegerField(default=0)
    percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    duration_seconds = models.PositiveIntegerField(default=0)
    started_at = models.DateTimeField(default=timezone.now)
    completed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-completed_at']
        indexes = [
            models.Index(fields=['user', 'classroom', 'completed_at'], name='vocab_quiz_scope_date'),
        ]

    def __str__(self):
        scope = self.classroom.name if self.classroom_id else 'Global'
        return f"{self.user.username} · {scope} · {self.score}/{self.total_questions}"


class VocabularyQuizAnswer(models.Model):
    attempt = models.ForeignKey(
        VocabularyQuizAttempt,
        on_delete=models.CASCADE,
        related_name='answers',
    )
    word = models.ForeignKey(
        VocabularyWord,
        on_delete=models.SET_NULL,
        related_name='quiz_answers',
        null=True,
        blank=True,
    )
    prompt = models.TextField()
    selected_answer = models.TextField(blank=True)
    correct_answer = models.TextField()
    is_correct = models.BooleanField(default=False)

    class Meta:
        ordering = ['id']

    def __str__(self):
        return f"Attempt {self.attempt_id} · {'Correct' if self.is_correct else 'Incorrect'}"



# Support teacher planning and reviews
class SupportTeacherProfile(BaseModel):
    """Public profile for teachers who can be booked by students for support lessons."""
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='support_teacher_profile'
    )
    display_name = models.CharField(max_length=255, blank=True)
    telegram_username = models.CharField(
        max_length=80,
        blank=True,
        help_text="Telegram username without @."
    )
    subjects = models.CharField(max_length=255, blank=True, help_text="Example: SAT Math, Reading, Writing")
    headline = models.CharField(
        max_length=180,
        blank=True,
        help_text="Short public headline, for example: SAT Math specialist.",
    )
    bio = models.TextField(blank=True)
    education = models.CharField(
        max_length=255,
        blank=True,
        help_text="University, degree, certification, or other public credential.",
    )
    languages = models.CharField(
        max_length=180,
        blank=True,
        help_text="Languages used during support lessons.",
    )
    years_experience = models.PositiveSmallIntegerField(
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(50)],
    )
    sat_total_score = models.PositiveSmallIntegerField(
        blank=True,
        null=True,
        validators=[MinValueValidator(400), MaxValueValidator(1600)],
    )
    sat_math_score = models.PositiveSmallIntegerField(
        blank=True,
        null=True,
        validators=[MinValueValidator(200), MaxValueValidator(800)],
    )
    sat_reading_writing_score = models.PositiveSmallIntegerField(
        blank=True,
        null=True,
        validators=[MinValueValidator(200), MaxValueValidator(800)],
    )
    scores_verified = models.BooleanField(
        default=False,
        help_text="Admin verification flag for publicly displayed SAT scores.",
    )
    meeting_link = models.URLField(
        blank=True,
        help_text="Default Google Meet, Zoom, or other lesson link shown for scheduled lessons.",
    )
    booking_instructions = models.CharField(
        max_length=255,
        blank=True,
        help_text="Short instruction shown before a student confirms a booking.",
    )
    min_booking_notice_hours = models.PositiveSmallIntegerField(
        default=2,
        validators=[MinValueValidator(0), MaxValueValidator(168)],
        help_text="Minimum notice required before a lesson can be booked.",
    )
    cancellation_notice_hours = models.PositiveSmallIntegerField(
        default=2,
        validators=[MinValueValidator(0), MaxValueValidator(168)],
        help_text="Students cannot cancel inside this notice window.",
    )
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_support_teacher_profiles'
    )

    class Meta:
        ordering = ['sort_order', 'display_name', 'user__first_name', 'user__username']
        verbose_name = "Support Teacher"
        verbose_name_plural = "Support Teachers"

    def __str__(self):
        return self.name

    def clean(self):
        super().clean()
        if self.sat_math_score and self.sat_reading_writing_score and self.sat_total_score:
            expected_total = self.sat_math_score + self.sat_reading_writing_score
            if self.sat_total_score != expected_total:
                raise ValidationError({
                    'sat_total_score': f'Total SAT score must equal Math + Reading & Writing ({expected_total}).'
                })

    @property
    def name(self):
        fallback = self.user.get_full_name() or self.user.username
        return self.display_name.strip() or fallback

    @property
    def clean_telegram_username(self):
        return (self.telegram_username or '').strip().lstrip('@')

    @property
    def telegram_url(self):
        username = self.clean_telegram_username
        if not username:
            return ''
        return f"https://t.me/{username}"

    @property
    def average_rating(self):
        annotated = getattr(self, 'display_avg_rating', None)
        if annotated is not None:
            return round(float(annotated), 1)
        value = self.reviews.filter(booking__status='completed').aggregate(avg=models.Avg('rating')).get('avg')
        return round(value, 1) if value is not None else None

    @property
    def reviews_count(self):
        annotated = getattr(self, 'display_reviews_count', None)
        if annotated is not None:
            return int(annotated)
        return self.reviews.filter(booking__status='completed').count()

    @property
    def completed_lessons_count(self):
        annotated = getattr(self, 'display_completed_lessons', None)
        if annotated is not None:
            return int(annotated)
        return self.bookings.filter(status='completed').count()

    @property
    def score_summary(self):
        rows = []
        if self.sat_total_score:
            rows.append(('SAT', self.sat_total_score))
        if self.sat_math_score:
            rows.append(('Math', self.sat_math_score))
        if self.sat_reading_writing_score:
            rows.append(('Reading & Writing', self.sat_reading_writing_score))
        return rows

    @property
    def profile_completion_percent(self):
        values = [
            self.display_name,
            self.headline,
            self.subjects,
            self.bio,
            self.education,
            self.languages,
            self.telegram_username,
        ]
        filled = sum(bool((value or '').strip()) for value in values)
        if self.sat_total_score or self.sat_math_score or self.sat_reading_writing_score:
            filled += 1
        return round((filled / 8) * 100)


class SupportTeacherAvailability(BaseModel):
    MONDAY = 0
    TUESDAY = 1
    WEDNESDAY = 2
    THURSDAY = 3
    FRIDAY = 4
    SATURDAY = 5
    SUNDAY = 6
    DAY_CHOICES = [
        (MONDAY, 'Monday'),
        (TUESDAY, 'Tuesday'),
        (WEDNESDAY, 'Wednesday'),
        (THURSDAY, 'Thursday'),
        (FRIDAY, 'Friday'),
        (SATURDAY, 'Saturday'),
        (SUNDAY, 'Sunday'),
    ]

    teacher = models.ForeignKey(
        SupportTeacherProfile,
        on_delete=models.CASCADE,
        related_name='availabilities'
    )
    day_of_week = models.PositiveSmallIntegerField(choices=DAY_CHOICES)
    start_time = models.TimeField()
    end_time = models.TimeField()
    slot_duration_minutes = models.PositiveSmallIntegerField(
        default=60,
        validators=[MinValueValidator(15), MaxValueValidator(180)],
        help_text="Length of each bookable lesson generated inside this weekly window.",
    )
    buffer_minutes = models.PositiveSmallIntegerField(
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(60)],
        help_text="Optional break between generated lesson slots.",
    )
    is_active = models.BooleanField(default=True)
    note = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ['day_of_week', 'start_time', 'end_time']
        unique_together = ('teacher', 'day_of_week', 'start_time', 'end_time')
        verbose_name = "Support Teacher Availability"
        verbose_name_plural = "Support Teacher Availabilities"

    def __str__(self):
        return f"{self.teacher.name} · {self.get_day_of_week_display()} {self.start_time:%H:%M}-{self.end_time:%H:%M}"

    def clean(self):
        super().clean()
        if self.start_time and self.end_time and self.end_time <= self.start_time:
            raise ValidationError("End time must be later than start time.")

        if self.start_time and self.end_time and self.slot_duration_minutes:
            start_minutes = self.start_time.hour * 60 + self.start_time.minute
            end_minutes = self.end_time.hour * 60 + self.end_time.minute
            if end_minutes - start_minutes < 15:
                raise ValidationError("Availability windows must be at least 15 minutes long.")

        if self.teacher_id and self.day_of_week is not None and self.start_time and self.end_time:
            overlap = SupportTeacherAvailability.objects.filter(
                teacher_id=self.teacher_id,
                day_of_week=self.day_of_week,
                start_time__lt=self.end_time,
                end_time__gt=self.start_time,
            )
            if self.is_active:
                overlap = overlap.filter(is_active=True)
            if self.pk:
                overlap = overlap.exclude(pk=self.pk)
            if overlap.exists():
                raise ValidationError("This availability window overlaps another window for the same day.")


class SupportLessonBooking(BaseModel):
    STATUS_SCHEDULED = 'scheduled'
    STATUS_COMPLETED = 'completed'
    STATUS_CANCELLED = 'cancelled'
    STATUS_NO_SHOW = 'no_show'
    STATUS_CHOICES = [
        (STATUS_SCHEDULED, 'Scheduled'),
        (STATUS_COMPLETED, 'Completed'),
        (STATUS_CANCELLED, 'Cancelled'),
        (STATUS_NO_SHOW, 'No-show'),
    ]

    TOPIC_GENERAL = 'general'
    TOPIC_MATH = 'math'
    TOPIC_READING_WRITING = 'reading_writing'
    TOPIC_TEST_STRATEGY = 'test_strategy'
    TOPIC_REVIEW = 'review'
    TOPIC_OTHER = 'other'
    TOPIC_CHOICES = [
        (TOPIC_GENERAL, 'General SAT support'),
        (TOPIC_MATH, 'SAT Math'),
        (TOPIC_READING_WRITING, 'Reading & Writing'),
        (TOPIC_TEST_STRATEGY, 'Test strategy'),
        (TOPIC_REVIEW, 'Review mistakes'),
        (TOPIC_OTHER, 'Other'),
    ]

    CANCELLED_BY_STUDENT = 'student'
    CANCELLED_BY_TEACHER = 'teacher'
    CANCELLED_BY_ADMIN = 'admin'
    CANCELLED_BY_CHOICES = [
        (CANCELLED_BY_STUDENT, 'Student'),
        (CANCELLED_BY_TEACHER, 'Support teacher'),
        (CANCELLED_BY_ADMIN, 'Administrator'),
    ]

    teacher = models.ForeignKey(
        SupportTeacherProfile,
        on_delete=models.CASCADE,
        related_name='bookings'
    )
    student = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='support_lesson_bookings'
    )
    start_at = models.DateTimeField(db_index=True)
    end_at = models.DateTimeField(db_index=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_SCHEDULED, db_index=True)
    topic = models.CharField(max_length=32, choices=TOPIC_CHOICES, default=TOPIC_GENERAL)
    student_note = models.TextField(blank=True)
    teacher_note = models.TextField(blank=True)
    meeting_link = models.URLField(blank=True)
    cancellation_reason = models.TextField(blank=True)
    cancelled_by = models.CharField(max_length=20, choices=CANCELLED_BY_CHOICES, blank=True)
    cancelled_at = models.DateTimeField(blank=True, null=True)
    marked_completed_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ['-start_at']
        indexes = [
            models.Index(fields=['teacher', 'status', 'start_at']),
            models.Index(fields=['student', 'status', 'start_at']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['teacher', 'start_at', 'end_at'],
                condition=models.Q(status='scheduled'),
                name='unique_scheduled_support_lesson_slot'
            )
        ]
        verbose_name = "Support Lesson Booking"
        verbose_name_plural = "Support Lesson Bookings"

    def __str__(self):
        return f"{self.student.username} → {self.teacher.name} · {self.start_at:%Y-%m-%d %H:%M}"

    @property
    def is_past(self):
        return timezone.now() >= self.end_at

    @property
    def is_live(self):
        current = timezone.now()
        return self.status == self.STATUS_SCHEDULED and self.start_at <= current < self.end_at

    @property
    def awaiting_confirmation(self):
        return self.status == self.STATUS_SCHEDULED and timezone.now() >= self.end_at

    @property
    def duration_minutes(self):
        if not self.start_at or not self.end_at:
            return 0
        return max(0, int((self.end_at - self.start_at).total_seconds() // 60))

    @property
    def student_can_cancel(self):
        if self.status != self.STATUS_SCHEDULED:
            return False
        notice_hours = self.teacher.cancellation_notice_hours if self.teacher_id else 0
        cutoff = self.start_at - timedelta(hours=notice_hours)
        return timezone.now() < cutoff

    @property
    def effective_meeting_link(self):
        return (self.meeting_link or self.teacher.meeting_link or '').strip()

    @property
    def can_receive_feedback(self):
        return (
            self.is_past
            and self.status == self.STATUS_COMPLETED
            and not hasattr(self, 'review')
        )

    def mark_completed_if_past(self):
        # v28: completion is an explicit teacher/admin action. A past lesson
        # stays scheduled ("awaiting confirmation") until it is marked
        # completed or no-show, preventing students from reviewing sessions
        # that may not have actually taken place.
        return False

    def clean(self):
        super().clean()
        if self.start_at and self.end_at and self.end_at <= self.start_at:
            raise ValidationError("End time must be later than start time.")


class SupportTeacherReview(BaseModel):
    booking = models.OneToOneField(
        SupportLessonBooking,
        on_delete=models.CASCADE,
        related_name='review'
    )
    teacher = models.ForeignKey(
        SupportTeacherProfile,
        on_delete=models.CASCADE,
        related_name='reviews'
    )
    student = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='support_teacher_reviews'
    )
    rating = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    feedback = models.TextField(blank=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Support Teacher Review"
        verbose_name_plural = "Support Teacher Reviews"

    def __str__(self):
        return f"{self.teacher.name} · {self.rating}/5 by {self.student.username}"

    @property
    def public_student_name(self):
        first_name = (self.student.first_name or '').strip()
        last_name = (self.student.last_name or '').strip()
        if first_name:
            return f"{first_name} {last_name[:1] + '.' if last_name else ''}".strip()
        username = (self.student.username or 'Student').strip()
        if len(username) <= 3:
            return username[:1] + '***'
        return username[:2] + '***' + username[-1:]

    def save(self, *args, **kwargs):
        if self.booking_id:
            self.teacher = self.booking.teacher
            self.student = self.booking.student
        super().save(*args, **kwargs)

class DreamUniversity(BaseModel):
    """Admin-managed university options shown in the student goal dashboard.

    SAT ranges change over time, so MakonBook stores the value as an editable
    planning reference instead of hard-coding admissions data in the UI.
    """
    name = models.CharField(max_length=180)
    country = models.CharField(max_length=120, blank=True)
    city = models.CharField(max_length=120, blank=True)
    average_sat_score = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(400), MaxValueValidator(1600)],
        help_text="Optional published or internally verified SAT reference. Do not invent values.",
    )
    qs_rank = models.PositiveSmallIntegerField(null=True, blank=True)
    ranking_source = models.CharField(max_length=120, blank=True, default='QS World University Rankings')
    ranking_year = models.PositiveSmallIntegerField(null=True, blank=True)
    score_note = models.CharField(
        max_length=180,
        blank=True,
        help_text="Optional context, for example: typical admitted-student range or internal target.",
    )
    website = models.URLField(blank=True)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['sort_order', 'name']
        verbose_name = 'Dream University'
        verbose_name_plural = 'Dream Universities'
        constraints = [
            models.UniqueConstraint(
                fields=['name', 'country'],
                name='sat_unique_dream_university_country',
            ),
        ]

    def __str__(self):
        return f"{self.name} ({self.country})" if self.country else self.name


class StudentGoalProfile(BaseModel):
    """A student's SAT destination, exam date, and sustainable study target."""
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='sat_goal_profile',
    )
    dream_university = models.ForeignKey(
        DreamUniversity,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='student_goals',
    )
    custom_university_name = models.CharField(max_length=180, blank=True)
    custom_university_country = models.CharField(max_length=120, blank=True)
    custom_average_sat_score = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(400), MaxValueValidator(1600)],
    )
    target_sat_score = models.PositiveSmallIntegerField(
        default=1400,
        validators=[MinValueValidator(400), MaxValueValidator(1600)],
    )
    exam_date = models.DateField(null=True, blank=True)
    daily_study_minutes_goal = models.PositiveSmallIntegerField(
        default=45,
        validators=[MinValueValidator(15), MaxValueValidator(360)],
    )
    weekly_study_days_goal = models.PositiveSmallIntegerField(
        default=5,
        validators=[MinValueValidator(1), MaxValueValidator(7)],
    )

    class Meta:
        verbose_name = 'Student SAT Goal'
        verbose_name_plural = 'Student SAT Goals'

    def __str__(self):
        destination = self.university_name or 'Goal not configured'
        return f"{self.user.username} → {destination}"

    def clean(self):
        super().clean()
        if self.exam_date and self.exam_date < timezone.localdate():
            raise ValidationError({'exam_date': 'Exam date cannot be in the past.'})
        if self.custom_university_name and not self.custom_average_sat_score and not self.dream_university_id:
            raise ValidationError({
                'custom_average_sat_score': 'Add an average SAT score for the custom university.'
            })

    @property
    def university_name(self):
        custom = (self.custom_university_name or '').strip()
        if custom:
            return custom
        return self.dream_university.name if self.dream_university_id else ''

    @property
    def university_country(self):
        custom = (self.custom_university_country or '').strip()
        if custom:
            return custom
        return self.dream_university.country if self.dream_university_id else ''

    @property
    def average_sat_score(self):
        if self.custom_university_name and self.custom_average_sat_score:
            return self.custom_average_sat_score
        if self.dream_university_id:
            return self.dream_university.average_sat_score
        return self.custom_average_sat_score

    @property
    def days_remaining(self):
        if not self.exam_date:
            return None
        return max(0, (self.exam_date - timezone.localdate()).days)

    @property
    def is_configured(self):
        return bool(self.university_name and self.exam_date and self.target_sat_score)


class Classroom(models.Model):
    CLASSROOM_TYPE_SAT = 'sat'
    CLASSROOM_TYPE_AP = 'ap'
    CLASSROOM_TYPE_CHOICES = (
        (CLASSROOM_TYPE_SAT, 'SAT Classroom'),
        (CLASSROOM_TYPE_AP, 'AP Classroom'),
    )

    teacher = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='owned_classrooms'
    )
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    classroom_type = models.CharField(
        max_length=10,
        choices=CLASSROOM_TYPE_CHOICES,
        default=CLASSROOM_TYPE_SAT,
        db_index=True,
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    @property
    def is_sat_classroom(self):
        return self.classroom_type == self.CLASSROOM_TYPE_SAT

    @property
    def is_ap_classroom(self):
        return self.classroom_type == self.CLASSROOM_TYPE_AP

    def __str__(self):
        return f"{self.name} ({self.get_classroom_type_display()} - {self.teacher.username})"


class ClassroomJoinCode(models.Model):
    classroom = models.OneToOneField(
        Classroom,
        on_delete=models.CASCADE,
        related_name='join_code'
    )
    code = models.CharField(max_length=6, unique=True)
    expires_at = models.DateTimeField()
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.classroom.name} - {self.code}"

    def is_valid(self):
        return self.is_active and timezone.now() < self.expires_at

    @staticmethod
    def default_expiry():
        return timezone.now() + timedelta(hours=12)


class ClassroomMembership(models.Model):
    ROLE_CHOICES = (
        ('teacher', 'Teacher'),
        ('student', 'Student'),
    )

    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('left', 'Left'),
        ('removed', 'Removed'),
    )

    classroom = models.ForeignKey(
        Classroom,
        on_delete=models.CASCADE,
        related_name='memberships'
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='classroom_memberships'
    )
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='student')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    requested_at = models.DateTimeField(auto_now_add=True)
    approved_at = models.DateTimeField(blank=True, null=True)
    left_at = models.DateTimeField(blank=True, null=True)
    removed_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        unique_together = ('classroom', 'user')
        ordering = ['-requested_at']

    def __str__(self):
        return f"{self.user.username} - {self.classroom.name} - {self.status}"


class StudentSectionAccess(models.Model):
    SECTION_CHOICES = (
        ('practice_tests', 'Practice Tests'),
        ('vocabulary', 'Vocabulary'),
        ('admissions', 'Admissions'),
    )

    membership = models.ForeignKey(
        ClassroomMembership,
        on_delete=models.CASCADE,
        related_name='section_access'
    )
    section = models.CharField(max_length=50, choices=SECTION_CHOICES)
    has_access = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('membership', 'section')
        ordering = ['section']

    def __str__(self):
        return f"{self.membership.user.username} - {self.section} - {self.has_access}"


class StudentProgress(models.Model):
    SECTION_CHOICES = (
        ('practice_tests', 'Practice Tests'),
        ('vocabulary', 'Vocabulary'),
        ('admissions', 'Admissions'),
    )

    classroom = models.ForeignKey(
        Classroom,
        on_delete=models.CASCADE,
        related_name='progress_records'
    )
    student = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='classroom_progress'
    )
    section = models.CharField(max_length=50, choices=SECTION_CHOICES)

    completion_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    completed_items = models.PositiveIntegerField(default=0)
    total_items = models.PositiveIntegerField(default=0)
    activity_count = models.PositiveIntegerField(default=0)
    last_activity_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        unique_together = ('classroom', 'student', 'section')
        ordering = ['student', 'section']
    
    def __str__(self):
        return f"{self.student.username} - {self.section} - {self.completion_percent}%"


class ChatMessage(models.Model):
    classroom = models.ForeignKey(
        Classroom,
        on_delete=models.CASCADE,
        related_name='chat_messages'
    )
    sender = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='sent_classroom_messages'
    )
    message = models.TextField(blank=True, null=True)
    file = models.FileField(upload_to='classroom_chat_files/', blank=True, null=True)
    is_deleted = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"{self.sender.username} - {self.classroom.name} - {self.created_at:%Y-%m-%d %H:%M}"
    


#GUEST MODE
class GlobalEvent(models.Model):
    EVENT_STATUS_CHOICES = [
        ("draft", "Draft"),
        ("scheduled", "Scheduled"),
        ("live", "Live"),
        ("closed", "Closed"),
    ]

    title = models.CharField(max_length=255)
    slug = models.SlugField(unique=True)
    description = models.TextField(blank=True)
    rules = models.TextField(blank=True)

    test = models.ForeignKey(
        "sat.Test",
        on_delete=models.CASCADE,
        related_name="global_events"
    )

    access_code = models.CharField(max_length=50, blank=True)
    is_public = models.BooleanField(default=True)

    start_at = models.DateTimeField()
    end_at = models.DateTimeField()
    duration_minutes = models.PositiveIntegerField(
        default=60,
        help_text="Fallback duration in minutes for each module if section-specific duration is not set."
    )
    english_duration_minutes = models.PositiveIntegerField(
        default=60,
        help_text="Duration in minutes for each English module."
    )
    math_duration_minutes = models.PositiveIntegerField(
        default=60,
        help_text="Duration in minutes for each Math module."
    )
    always_live = models.BooleanField(default=False, help_text="If checked, event is available 24/7 regardless of start/end times")

    status = models.CharField(
        max_length=20,
        choices=EVENT_STATUS_CHOICES,
        default="draft"
    )

    show_score_immediately = models.BooleanField(default=True)
    show_leaderboard = models.BooleanField(default=False)
    allow_resume = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def is_live_now(self):
        now = timezone.now()
        if self.always_live:
            return self.is_public and self.status == "live"
        return (
            self.is_public and
            self.status == "live" and
            self.start_at <= now <= self.end_at
        )

    def get_module_duration(self, section):
        if section == "english":
            return self.english_duration_minutes or self.duration_minutes
        if section == "math":
            return self.math_duration_minutes or self.duration_minutes
        return self.duration_minutes

    def clean(self):
        super().clean()
        if not self.always_live and self.start_at and self.end_at and self.end_at <= self.start_at:
            raise ValidationError({"end_at": "Event end time must be later than its start time."})
        if self.access_code:
            self.access_code = self.access_code.strip()

    def __str__(self):
        return self.title

class GuestParticipant(models.Model):
    guest_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)

    full_name = models.CharField(max_length=255)
    display_name = models.CharField(max_length=255, blank=True)

    session_key = models.CharField(max_length=255, blank=True)
    first_ip = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.display_name or self.full_name
    
class GlobalEventAttempt(models.Model):
    ATTEMPT_STATUS_CHOICES = [
        ("in_progress", "In Progress"),
        ("submitted", "Submitted"),
        ("expired", "Expired"),
    ]

    event = models.ForeignKey(
        "sat.GlobalEvent",
        on_delete=models.CASCADE,
        related_name="attempts"
    )
    guest = models.ForeignKey(
        "sat.GuestParticipant",
        on_delete=models.CASCADE,
        related_name="attempts"
    )

    guest_token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)

    started_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    submitted_at = models.DateTimeField(null=True, blank=True)
    current_module_started_at = models.DateTimeField(null=True, blank=True, help_text="When the current module started")

    status = models.CharField(
        max_length=20,
        choices=ATTEMPT_STATUS_CHOICES,
        default="in_progress"
    )

    score = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    raw_score = models.IntegerField(null=True, blank=True)

    total_questions = models.PositiveIntegerField(default=0)
    answered_questions = models.PositiveIntegerField(default=0)
    completed_modules = models.JSONField(default=list, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["event", "guest"],
                name="unique_guest_attempt_per_event"
            )
        ]

    def get_time_left_seconds(self, section=None):
        """Calculate time remaining for the current module/section."""
        module_start = self.current_module_started_at or self.started_at
        elapsed = (timezone.now() - module_start).total_seconds()

        if section:
            module_duration_seconds = self.event.get_module_duration(section) * 60
        else:
            module_duration_seconds = self.event.duration_minutes * 60

        return max(0, int(module_duration_seconds - elapsed))

    @property
    def time_left_seconds(self):
        return self.get_time_left_seconds()

    def __str__(self):
        return f"{self.guest} - {self.event}"


class GlobalEventModuleDraft(models.Model):
    """Server-authoritative resumable state for a guest event module.

    Guest answers were previously written directly to ``GlobalEventAnswer`` while
    UI-only state (current question, eliminated choices, marks) lived only in the
    browser.  This row mirrors the regular SAT ``TestModuleDraft`` flow so refresh,
    another device, and an expired timer all resolve from one consistent snapshot.
    The row is deleted after the module is submitted.
    """
    attempt = models.ForeignKey(
        "sat.GlobalEventAttempt",
        on_delete=models.CASCADE,
        related_name="module_drafts",
    )
    section = models.CharField(max_length=8)
    module = models.CharField(max_length=8)
    answers = models.JSONField(default=list, blank=True)
    time_spent = models.JSONField(default=list, blank=True)
    eliminated_choices = models.JSONField(default=list, blank=True)
    marked_for_review = models.JSONField(default=list, blank=True)
    current_question_index = models.PositiveIntegerField(default=0)
    deadline_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["attempt", "section", "module"],
                name="unique_guest_event_module_draft",
            )
        ]
        indexes = [
            models.Index(fields=["attempt", "section", "module"], name="guest_draft_attempt_step"),
            models.Index(fields=["deadline_at"], name="guest_draft_deadline"),
        ]

    def __str__(self):
        return f"{self.attempt_id}:{self.section}:{self.module}"


class GlobalEventAnswer(models.Model):
    SECTION_CHOICES = [
        ("english", "English"),
        ("math", "Math"),
    ]

    attempt = models.ForeignKey(
        "sat.GlobalEventAttempt",
        on_delete=models.CASCADE,
        related_name="answers"
    )

    section = models.CharField(max_length=20, choices=SECTION_CHOICES)
    module = models.CharField(max_length=10, blank=True)
    question_id = models.PositiveIntegerField()
    selected_answer = models.TextField(blank=True, null=True)

    is_correct = models.BooleanField(null=True, blank=True)
    time_spent = models.PositiveIntegerField(default=0)

    answered_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["attempt", "section", "module", "question_id"],
                name="unique_global_answer_per_question"
            )
        ]

    def __str__(self):
        return f"{self.attempt} - {self.section} - Q{self.question_id}"

class StudentPracticeTestAccess(models.Model):
    membership = models.ForeignKey(
        ClassroomMembership,
        on_delete=models.CASCADE,
        related_name='practice_test_access'
    )
    test = models.ForeignKey(
        Test,
        on_delete=models.CASCADE,
        related_name='student_practice_access'
    )
    has_access = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('membership', 'test')
        ordering = ['test__name']

    def __str__(self):
        return f"{self.membership.user.username} - {self.test.name} - {self.has_access}"