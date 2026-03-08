from django.db import models
from django.contrib.auth.models import User, Group
from datetime import timedelta, timezone
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
from .store import PublicStorage, PrivateStorage  # Replace with your actual storage backend import

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

    def get_number(self):
        return int(self.name)

    def __str__(self):
        return self.name

# Choices for modules
modules = [('module_1', "Module 1"), ('module_2', "Module 2")]

# English questions
class English_Question(BaseModel):
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
    graph = models.BooleanField('Is there Graph or Table', default=False)
    answer = models.CharField('Answer', null=True, blank=True, max_length=400)
    explained = models.TextField('Explanation', blank=True, null=True)

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
            return f"IMAGE::{self.image_a.url}"
        return self.a

    def get_b(self):
        if self.choice_graph and self.image_b:
            return f"IMAGE::{self.image_b.url}"
        return self.b

    def get_c(self):
        if self.choice_graph and self.image_c:
            return f"IMAGE::{self.image_c.url}"
        return self.c

    def get_d(self):
        if self.choice_graph and self.image_d:
            return f"IMAGE::{self.image_d.url}"
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
    section = models.CharField(max_length=8)
    module = models.CharField(choices=[('m1', 'Module 1'), ('m2', 'Module 2')], max_length=8, blank=True, null=True)
    answers = models.TextField(blank=True, null=True)
    created = models.DateTimeField(auto_now_add=True, null=True)
    
    TEST_TYPE_CHOICES = [
        ('regular', 'Regular Test'),
        ('makeup', 'Makeup Test'),
    ]
    test_type = models.CharField(max_length=20, choices=TEST_TYPE_CHOICES, default='regular')

    def find_answer(self, question_id):
        previous, now, future = '', '', ''
        for item in json.loads(self.answers or '{"answers": []}')['answers']:
            if now:
                future = item['questionID']
                break
            if item['questionID'] == question_id:
                now = item['answer']
            else:
                previous = item['questionID']
        return previous, now, future

    def __str__(self):
        return f'{self.user}>{self.test}_{self.section}_{self.module}'

    class Meta:
        unique_together = ('user', 'test', 'makeup_test', 'section', 'module')

# Test review and scoring
class TestReview(BaseModel):
    test = models.ForeignKey(Test, on_delete=models.SET_NULL, null=True, blank=True, related_name="test_reviews")
    makeup_test = models.ForeignKey(MakeupTest, on_delete=models.SET_NULL, null=True, blank=True, related_name="makeup_test_reviews")
    user = models.ForeignKey(User, null=True, on_delete=models.CASCADE)
    key = models.CharField(max_length=100, blank=True, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    duration = models.DurationField(default=timedelta(hours=24))
    score = models.IntegerField(default=400,null=True)
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
        # Admin users get unlimited review time
        if self.user.groups.filter(name='Admin').exists():
            return True
        # OFFLINE group users get infinite review time
        if self.user.groups.filter(name='OFFLINE').exists():
            return True
        # Regular users follow the duration limit
        return self.created_at + self.duration > datetime.datetime.now(timezone.utc)

    def update_key(self):
        self.key = ''.join(random.choices(string.ascii_letters, k=100))
        self.save()

    def __str__(self):
        return f"{self.user.username} - {self.test} - {self.score}"

# Test stages for user progress
class TestStage(BaseModel):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    test = models.ForeignKey(Test, on_delete=models.SET_NULL, null=True, blank=True, related_name="test_stages")
    makeup_test = models.ForeignKey(MakeupTest, on_delete=models.SET_NULL, null=True, blank=True, related_name="makeup_test_stages")
    stage = models.IntegerField()
    again = models.BooleanField(default=True)
    retake_count = models.IntegerField(default=0, help_text="Number of retakes used by this user")
    
    TEST_TYPE_CHOICES = [
        ('regular', 'Regular Test'),
        ('makeup', 'Makeup Test'),
    ]
    test_type = models.CharField(max_length=20, choices=TEST_TYPE_CHOICES, default='regular')

    def get_max_retakes(self):
        """Get maximum retakes allowed for this user based on their group."""
        if self.user.groups.filter(name='OFFLINE').exists():
            return 4
        return 2

    def resolve(self):
        """Reset the test if retakes are available."""
        max_retakes = self.get_max_retakes()
        
        if self.retake_count < max_retakes:
            self.stage = 0
            self.delete_related()
            self.retake_count += 1
            self.save()
            return True
        return False

    def resolve_section(self, section):
        """Delete modules for a specific section and reset stage accordingly."""
        max_retakes = self.get_max_retakes()
        
        if self.retake_count < max_retakes:
            # Delete only the modules for the specified section
            modules_to_delete = TestModule.objects.filter(
                test=self.test, 
                makeup_test=self.makeup_test,
                user=self.user, 
                section=section
            )
            for module in modules_to_delete:
                module.delete()
            
            # Reset stage to the beginning of the specified section
            if section == 'english':
                self.stage = 1  # Reset to English Module 1
            elif section == 'math':
                self.stage = 3  # Reset to Math Module 1
            
            self.retake_count += 1
            self.save()
            return True
        return False

    def get_retakes_remaining(self):
        """Get number of retakes remaining for this user."""
        max_retakes = self.get_max_retakes()
        return max_retakes - self.retake_count

    def next_stage(self):
        if self.stage == 4:
            return True
        self.stage += 1
        self.save()
        return False

    def delete_related(self):
        all_modules = TestModule.objects.filter(test=self.test, user=self.user)
        for module in all_modules:
            module.delete()
        all_review = TestReview.objects.filter(test=self.test, user=self.user)
        for review in all_review:
            review.delete()

    def get_models(self):
        if self.test_type == 'regular' and self.test:
            section = 'english' if self.stage <= 2 else 'math'
            module = 'm1' if self.stage in [1, 3] else 'm2'
            return self.test, section, module
        elif self.test_type == 'makeup' and self.makeup_test:
            section = 'english' if self.stage <= 2 else 'math'
            module = 'm1' if self.stage in [1, 3] else 'm2'
            return self.makeup_test, section, module

    def __str__(self):
        return f'{self.user}->{self.test}'

    class Meta:
        unique_together = ('user', 'test')

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
    instance.delete_related()