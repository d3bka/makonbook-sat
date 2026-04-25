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
from .storages import PublicStorage, PrivateStorage  # Replace with your actual storage backend import
from django.utils import timezone

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

# Test review and scoring
class TestReview(BaseModel):
    test = models.ForeignKey(Test, on_delete=models.SET_NULL, null=True, blank=True, related_name="test_reviews")
    makeup_test = models.ForeignKey(MakeupTest, on_delete=models.SET_NULL, null=True, blank=True, related_name="makeup_test_reviews")
    user = models.ForeignKey(User, null=True, on_delete=models.CASCADE)
    key = models.CharField(max_length=100, blank=True, unique=True)
    attempt_id = models.UUIDField(default=uuid.uuid4, editable=False)
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
        return self.created_at + self.duration > timezone.now()

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
    stage = models.IntegerField()
    again = models.BooleanField(default=True)
    retake_count = models.IntegerField(default=0, help_text="Number of retakes used by this user")
    attempt_id = models.UUIDField(default=uuid.uuid4, editable=False)

<<<<<<< HEAD
    TEST_TYPE_CHOICES = [
        ('regular', 'Regular Test'),
        ('makeup', 'Makeup Test'),
    ]
    test_type = models.CharField(max_length=20, choices=TEST_TYPE_CHOICES, default='regular')
=======
        # Validate the code
        if not code or len(code) != 6 or not code.isdigit():
            messages.error(request, "Please enter a valid 6-digit code using numbers only.")
        else:
            try:
                try:
                    from apps.apclasses.models import APExamEvent
                except Exception:
                    APExamEvent = None

                if APExamEvent is not None:
                    ap_event = (
                        APExamEvent.objects
                        .filter(access_code=code)
                        .exclude(access_code="")
                        .first()
                    )
                    if ap_event:
                        request.session[f"ap_event_{ap_event.pk}_secret_ok"] = True
                        messages.success(request, f"Access granted for AP event: {ap_event.title}")
                        return redirect('apclasses:start_event', slug=ap_event.slug)

                secret_code = SecretCode.objects.get(code=code)
                user = request.user
                
                # Add user to the specified group if not already a member
                if secret_code.group not in user.groups.all():
                    user.groups.add(secret_code.group)
                    user.save()
                    messages.success(request, f"You have been added to the '{secret_code.group.name}' group!")
                else:
                    messages.info(request, "You are already in this group.")
>>>>>>> d34b18b (Added AP Course)

    def get_max_retakes(self):
        # unlimited
        return None

    def invalidate_review(self):
        """
        Keep the review row, but mark it unavailable while a new attempt is in progress.
        This prevents stale review links from crashing with Invalid Key.
        """
        reviews = TestReview.objects.filter(test=self.test, user=self.user)
        for review in reviews:
            review.score = None
            review.certificate = ''
            review.save(update_fields=['score', 'certificate'])

    class Meta:
        indexes = [
            models.Index(fields=['user', 'test', 'created_at'], name='sat_ts_u_t_cr'),
            models.Index(fields=['user', 'test', 'attempt_id'], name='sat_ts_u_t_att'),
        ]

    def delete_modules(self, section=None):
        """Delete TestModule records for this test."""
        modules = TestModule.objects.filter(test=self.test, user=self.user)
        if section:
            modules = modules.filter(section=section)
        modules.delete()

    def resolve(self):
        """
        Full test restart. With unlimited retakes (max_retakes=None), always allows restart.
        """
        max_retakes = self.get_max_retakes()
        
<<<<<<< HEAD
        # For unlimited retakes, max_retakes is None, so always allow
        if max_retakes is not None and self.retake_count >= max_retakes:
            self.again = False
            self.save(update_fields=['again'])
            return False
        
        self.stage = 1
        self.delete_modules()
        self.invalidate_review()
        self.retake_count += 1
        self.attempt_id = uuid.uuid4()
        self.save(update_fields=['stage', 'retake_count', 'attempt_id'])
=======
        return render(request, 'sat/retake_limit_exceeded.html', {
            'test_name': pk,
            'section': section,
            'retakes_used': stage.retake_count,
            'max_retakes': stage.get_max_retakes(),
            'user_group': user_group
        })


@login_required(login_url='/login/')
def vocabulary(request):
    units = VocabularyUnit.objects.filter(is_active=True).prefetch_related('words').order_by('order', 'id')

    return render(request, 'sat/vocabulary.html', {
        'units': units
    })


ADMISSIONS_SECTIONS = {
    "university_guide": {
        "title": "University Guide",
        "description": "Basic guidance for choosing universities and programs.",
        "items": [
            {
                "title": "How to Compare Universities",
                "content": [
                    "Check tuition and total cost, not just headline tuition.",
                    "Look at major strength, not just university ranking.",
                    "Check scholarship availability for international students.",
                    "Compare location, campus size, and internship access.",
                    "Look at graduation outcomes and career support.",
                ]
            },
            {
                "title": "What to Research",
                "content": [
                    "Application deadlines",
                    "Required English test scores",
                    "SAT/optional policy",
                    "Financial aid for internationals",
                    "Major-specific requirements",
                ]
            },
        ]
    },
    "application_help": {
        "title": "Application Help",
        "description": "Step-by-step help for preparing your college applications.",
        "items": [
            {
                "title": "Core Application Checklist",
                "content": [
                    "Create university account/Common App account",
                    "Prepare passport and personal details",
                    "Add school and academic information",
                    "Prepare IELTS/TOEFL scores",
                    "Prepare SAT scores if needed",
                    "Write personal essay",
                    "Request recommendation letters",
                    "Upload transcripts",
                ]
            },
            {
                "title": "Essay Advice",
                "content": [
                    "Be specific, not generic",
                    "Show personal growth",
                    "Avoid fake drama",
                    "Use real examples",
                    "Keep structure clear",
                ]
            },
        ]
    },
    "scholarships": {
        "title": "Scholarships",
        "description": "Basic overview of scholarship planning.",
        "items": [
            {
                "title": "Common Scholarship Types",
                "content": [
                    "Merit scholarships",
                    "Need-based aid",
                    "International student grants",
                    "Department scholarships",
                    "External private scholarships",
                ]
            },
            {
                "title": "What Usually Helps",
                "content": [
                    "Strong GPA",
                    "High English proficiency scores",
                    "Strong SAT if required",
                    "Good essay",
                    "Clear extracurricular profile",
                    "Early application",
                ]
            },
        ]
    },
}


@login_required(login_url='/login/')
def vocabulary_section(request, slug):

    units = VocabularyUnit.objects.filter(is_active=True).prefetch_related('words').order_by('order', 'id')

    if slug == 'word_lists':
        return render(request, 'sat/vocabulary_word_lists.html', {
            'units': units
        })

    if slug == 'flashcards':
        return render(request, 'sat/vocabulary_flashcards.html', {
            'units': units
        })

    raise Http404("Vocabulary section not found")


@login_required(login_url='/login/')
def admissions(request):
    return render(request, 'sat/admissions.html', {
        'sections': ADMISSIONS_SECTIONS
    })


@login_required(login_url='/login/')
def admissions_section(request, slug):

    section = ADMISSIONS_SECTIONS.get(slug)
    if not section:
        raise Http404("Admissions section not found")

    return render(request, 'sat/admissions_section.html', {
        'slug': slug,
        'section': section,
    })

@login_required(login_url='/login/')
def vocabulary_practice_quiz(request):

    units = VocabularyUnit.objects.filter(is_active=True).prefetch_related('words').order_by('order', 'id')

    return render(request, 'sat/vocabulary_practice_quiz.html', {
        'units': units
    })

@login_required(login_url='/login/')
def vocabulary_practice_quiz_start(request):

    if request.method != 'POST':
        return redirect('vocabulary_practice_quiz')

    selected_ids = request.POST.getlist('units')
    selected_ids = [int(x) for x in selected_ids if x.isdigit()]
    requested_count = request.POST.get('question_count')

    if not selected_ids:
        messages.error(request, "Select at least one unit.")
        return redirect('vocabulary_practice_quiz')

    try:
        requested_count = int(requested_count)
    except (TypeError, ValueError):
        messages.error(request, "Enter a valid number of questions.")
        return redirect('vocabulary_practice_quiz')

    selected_units = VocabularyUnit.objects.filter(
        id__in=selected_ids,
        is_active=True
    ).prefetch_related('words')

    selected_words = []
    for unit in selected_units:
        for word in unit.words.filter(is_active=True):
            selected_words.append(word)

    if len(selected_words) < 4:
        messages.error(request, "You need at least 4 words in the selected units to generate a quiz.")
        return redirect('vocabulary_practice_quiz')

    max_available = len(selected_words)

    if requested_count < 1:
        messages.error(request, "Question count must be at least 1.")
        return redirect('vocabulary_practice_quiz')

    if requested_count > max_available:
        messages.error(request, f"You selected {requested_count} questions, but only {max_available} words are available.")
        return redirect('vocabulary_practice_quiz')

    random.shuffle(selected_words)
    test_words = selected_words[:requested_count]

    all_meanings_pool = [w.meaning for w in selected_words]

    questions = []
    for word_obj in test_words:
        correct_answer = word_obj.meaning

        wrong_answers = [m for m in all_meanings_pool if m != correct_answer]
        wrong_answers = list(set(wrong_answers))
        random.shuffle(wrong_answers)
        wrong_answers = wrong_answers[:3]

        if len(wrong_answers) < 3:
            continue

        choices = [correct_answer] + wrong_answers
        random.shuffle(choices)

        questions.append({
            'unit': word_obj.unit.title,
            'question': f"What is the meaning of '{word_obj.word}'?",
            'choices': choices,
            'answer': correct_answer,
            'word': word_obj.word,
        })

    if not questions:
        messages.error(request, "Could not generate quiz questions from selected words.")
        return redirect('vocabulary_practice_quiz')

    request.session['vocab_quiz_questions'] = questions
    request.session['vocab_quiz_units'] = [u.title for u in selected_units]

    return render(request, 'sat/vocabulary_practice_quiz_test.html', {
        'questions': questions,
        'selected_units': selected_units,
        'requested_count': len(questions),
    })


@login_required(login_url='/login/')
def vocabulary_practice_quiz_result(request):

    if request.method != 'POST':
        return redirect('vocabulary_practice_quiz')

    questions = request.session.get('vocab_quiz_questions', [])
    score = 0
    total_questions = len(questions)
    results = []

    for i, q in enumerate(questions):
        user_answer = request.POST.get(f'question_{i}')
        is_correct = user_answer == q['answer']

        if is_correct:
            score += 1

        results.append({
            'unit': q['unit'],
            'question': q['question'],
            'correct_answer': q['answer'],
            'user_answer': user_answer,
            'is_correct': is_correct,
            'word': q.get('word', ''),
        })

    percentage = (score / total_questions * 100) if total_questions > 0 else 0

    # Clear session data
    request.session.pop('vocab_quiz_questions', None)
    request.session.pop('vocab_quiz_units', None)
    request.session.pop('vocab_quiz_classroom_id', None)

    return render(request, 'sat/vocabulary_practice_quiz_result.html', {
        'results': results,
        'score': score,
        'total': total_questions,
        'total_questions': total_questions,
        'percentage': percentage,
        'selected_units': request.session.get('vocab_quiz_units', []),
    })

@login_required(login_url='/login/')
def vocabulary_flashcards(request):

    units = VocabularyUnit.objects.filter(is_active=True).prefetch_related('words').order_by('order', 'id')

    return render(request, 'sat/vocabulary_flashcards.html', {
        'units': units
    })

def is_teacher(user):
    return (
        user.is_superuser
        or user.is_staff
        or user.groups.filter(name='teacher').exists()
    )


def generate_6_digit_code():
    return f"{random.randint(0, 999999):06d}"


def generate_unique_classroom_code():
    while True:
        code = generate_6_digit_code()
        if not ClassroomJoinCode.objects.filter(code=code, is_active=True).exists():
            return code

@login_required(login_url='/login/')
def teacher_classroom_list(request):
    if not is_teacher(request.user):
        return HttpResponseForbidden("Only teachers can access classroom management.")

    classrooms = Classroom.objects.filter(teacher=request.user).order_by('-created_at')

    return render(request, 'sat/teacher_classroom_list.html', {
        'classrooms': classrooms,
    })

@login_required(login_url='/login/')
def update_student_practice_test_access(request, classroom_id, user_id):
    classroom = get_object_or_404(Classroom, id=classroom_id)

    if classroom.teacher != request.user and not request.user.is_superuser:
        return HttpResponseForbidden("You can manage only your own classrooms.")

    membership = get_object_or_404(
        ClassroomMembership,
        classroom=classroom,
        user_id=user_id,
        role='student',
        status='approved'
    )

    tests = Test.objects.all().distinct().order_by('name')

    if request.method == 'POST':
        access_mode = request.POST.get('access_mode', 'all')
        selected_test_names = request.POST.getlist('tests')

        access_map = get_membership_section_access_map(membership)
        if not access_map.get('practice_tests'):
            messages.error(request, "First enable Practice Tests section access for this student.")
            return redirect(
                'update_student_practice_test_access',
                classroom_id=classroom.id,
                user_id=user_id
            )

        StudentPracticeTestAccess.objects.filter(membership=membership).delete()

        if access_mode == 'selected':
            selected_tests = Test.objects.filter(pk__in=selected_test_names).distinct()

            for test in selected_tests:
                StudentPracticeTestAccess.objects.update_or_create(
                    membership=membership,
                    test=test,
                    defaults={'has_access': True}
                )

        messages.success(request, "Student practice test access updated successfully.")
        return redirect('teacher_classroom_dashboard', classroom_id=classroom.id)

    existing_items = StudentPracticeTestAccess.objects.filter(
        membership=membership,
        has_access=True
    )

    selected_test_ids = set(existing_items.values_list('test_id', flat=True))
    access_mode = 'selected' if existing_items.exists() else 'all'

    return render(request, 'sat/update_student_practice_test_access.html', {
        'classroom': classroom,
        'membership': membership,
        'tests': tests,
        'selected_test_ids': selected_test_ids,
        'access_mode': access_mode,
    })

@login_required(login_url='/login/')
def create_classroom(request):
    if not is_teacher(request.user):
        return HttpResponseForbidden("Only teachers can create classrooms.")

    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        description = request.POST.get('description', '').strip()

        if not name:
            messages.error(request, "Classroom name is required.")
            return redirect('create_classroom')

        classroom = Classroom.objects.create(
            teacher=request.user,
            name=name,
            description=description,
            is_active=True,
        )

        # create teacher membership automatically
        ClassroomMembership.objects.get_or_create(
            classroom=classroom,
            user=request.user,
            defaults={
                'role': 'teacher',
                'status': 'approved',
                'approved_at': timezone.now(),
            }
        )

        messages.success(request, f'Classroom "{classroom.name}" created successfully.')
        return redirect('teacher_classroom_dashboard', classroom_id=classroom.id)

    return render(request, 'sat/create_classroom.html')

@login_required(login_url='/login/')
def teacher_classroom_dashboard(request, classroom_id):
    classroom = get_object_or_404(Classroom, id=classroom_id)

    if classroom.teacher != request.user and not request.user.is_superuser:
        return HttpResponseForbidden("You can manage only your own classrooms.")

    students = ClassroomMembership.objects.filter(
        classroom=classroom,
        role='student'
    ).select_related('user').order_by('-requested_at')

    join_code = getattr(classroom, 'join_code', None)

    return render(request, 'sat/teacher_classroom_dashboard.html', {
        'classroom': classroom,
        'students': students,
        'join_code': join_code,
    })

@login_required(login_url='/login/')
def generate_classroom_join_code(request, classroom_id):
    classroom = get_object_or_404(Classroom, id=classroom_id)

    if classroom.teacher != request.user and not request.user.is_superuser:
        return HttpResponseForbidden("You can manage only your own classrooms.")

    old_code = ClassroomJoinCode.objects.filter(classroom=classroom).first()
    if old_code:
        old_code.is_active = False
        old_code.save()

    new_code = generate_unique_classroom_code()

    ClassroomJoinCode.objects.update_or_create(
        classroom=classroom,
        defaults={
            'code': new_code,
            'expires_at': timezone.now() + timedelta(hours=12),
            'is_active': True,
        }
    )

    messages.success(request, f"New join code generated for {classroom.name}.")
    return redirect('teacher_classroom_dashboard', classroom_id=classroom.id)

def get_user_approved_student_membership(user):
    return ClassroomMembership.objects.filter(
        user=user,
        role='student',
        status='approved'
    ).select_related('classroom').first()


def get_user_pending_student_membership(user):
    return ClassroomMembership.objects.filter(
        user=user,
        role='student',
        status='pending'
    ).select_related('classroom').first()


def is_student(user):
    return user.groups.filter(name='student').exists() or not is_teacher(user)


def get_client_ip(request):
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', 'unknown')


def is_join_code_rate_limited(request):
    ip = get_client_ip(request)
    key = f"classroom_join_attempts:{ip}"
    attempts = cache.get(key, 0)
    return attempts >= 5


def register_join_code_attempt(request):
    ip = get_client_ip(request)
    key = f"classroom_join_attempts:{ip}"
    attempts = cache.get(key, 0)
    cache.set(key, attempts + 1, timeout=600)  # 10 minutes

@login_required(login_url='/login/')
def classroom_entry(request):
    if is_teacher(request.user):
        return redirect('teacher_classroom_list')

    approved_membership = ClassroomMembership.objects.filter(
        user=request.user,
        role='student',
        status='approved'
    ).select_related('classroom').first()

    if approved_membership:
        if approved_membership.classroom and approved_membership.classroom.is_active:
            return redirect('student_classroom_home', classroom_id=approved_membership.classroom.id)

    pending_membership = ClassroomMembership.objects.filter(
        user=request.user,
        role='student',
        status='pending'
    ).select_related('classroom').first()

    rejected_membership = ClassroomMembership.objects.filter(
        user=request.user,
        role='student',
        status='rejected'
    ).select_related('classroom').order_by('-requested_at').first()

    return render(request, 'sat/classroom_join.html', {
        'pending_membership': pending_membership,
        'rejected_membership': rejected_membership,
    })

@login_required(login_url='/login/')
def submit_classroom_join_request(request):
    if request.method != 'POST':
        return redirect('sat_menu')

    if is_teacher(request.user):
        return HttpResponseForbidden("Teachers cannot submit classroom join requests.")

    approved_membership = get_user_approved_student_membership(request.user)
    if approved_membership:
        messages.error(request, "You are already enrolled in a classroom.")
        return redirect('student_classroom_home', classroom_id=approved_membership.classroom.id)

    existing_pending = get_user_pending_student_membership(request.user)
    if existing_pending:
        messages.info(request, "You already have a pending classroom request.")
        return redirect('sat_menu')

    if is_join_code_rate_limited(request):
        messages.error(request, "Too many code attempts. Please wait and try again later.")
        return redirect('sat_menu')

    code = request.POST.get('join_code', '').strip()

    if not code.isdigit() or len(code) != 6:
        register_join_code_attempt(request)
        messages.error(request, "Code must contain exactly 6 digits.")
        return redirect('sat_menu')

    join_code = ClassroomJoinCode.objects.filter(
        code=code,
        is_active=True
    ).select_related('classroom').first()

    if not join_code or not join_code.is_valid():
        register_join_code_attempt(request)
        messages.error(request, "Invalid or expired classroom code.")
        return redirect('sat_menu')

    membership, created = ClassroomMembership.objects.get_or_create(
        classroom=join_code.classroom,
        user=request.user,
        defaults={
            'role': 'student',
            'status': 'pending',
        }
    )

    if not created:
        if membership.status == 'approved':
            messages.error(request, "You are already enrolled in this classroom.")
        elif membership.status == 'pending':
            messages.info(request, "Your request is already pending.")
        elif membership.status == 'rejected':
            membership.status = 'pending'
            membership.requested_at = timezone.now()
            membership.approved_at = None
            membership.save()
            messages.success(request, "Your join request has been submitted again.")
        return redirect('sat_menu')

    messages.success(request, f'Join request sent to classroom "{join_code.classroom.name}".')
    return redirect('sat_menu')

@login_required(login_url='/login/')
def classroom_join_status(request):
    approved_membership = get_user_approved_student_membership(request.user)
    if approved_membership:
        return redirect('student_classroom_home', classroom_id=approved_membership.classroom.id)

    pending_membership = get_user_pending_student_membership(request.user)

    rejected_membership = ClassroomMembership.objects.filter(
        user=request.user,
        role='student',
        status='rejected'
    ).select_related('classroom').order_by('-requested_at').first()

    return render(request, 'sat/classroom_join_status.html', {
        'pending_membership': pending_membership,
        'rejected_membership': rejected_membership,
    })

@login_required(login_url='/login/')
def classroom_join_requests(request, classroom_id):
    classroom = get_object_or_404(Classroom, id=classroom_id)

    if classroom.teacher != request.user and not request.user.is_superuser:
        return HttpResponseForbidden("You can manage only your own classrooms.")

    requests_qs = ClassroomMembership.objects.filter(
        classroom=classroom,
        role='student',
        status='pending'
    ).select_related('user').order_by('-requested_at')

    return render(request, 'sat/teacher_classroom_dashboard.html', {
        'classroom': classroom,
        'students': ClassroomMembership.objects.filter(
            classroom=classroom,
            role='student'
        ).select_related('user').order_by('-requested_at'),
        'join_code': getattr(classroom, 'join_code', None),
        'pending_requests': requests_qs,
    })

@login_required(login_url='/login/')
def approve_join_request(request, classroom_id, membership_id):
    classroom = get_object_or_404(Classroom, id=classroom_id)

    if classroom.teacher != request.user and not request.user.is_superuser:
        return HttpResponseForbidden("You can manage only your own classrooms.")

    membership = get_object_or_404(
        ClassroomMembership,
        id=membership_id,
        classroom=classroom,
        role='student'
    )

    existing_approved = ClassroomMembership.objects.filter(
        user=membership.user,
        role='student',
        status='approved'
    ).exclude(id=membership.id).first()

    if existing_approved:
        messages.error(request, "This student already belongs to another approved classroom.")
        return redirect('teacher_classroom_dashboard', classroom_id=classroom.id)

    membership.status = 'approved'
    membership.approved_at = timezone.now()
    membership.save()

    for section in ['practice_tests', 'vocabulary', 'admissions']:
        StudentSectionAccess.objects.get_or_create(
            membership=membership,
            section=section,
            defaults={'has_access': False}
        )

    messages.success(request, f"{membership.user.username} has been approved.")
    return redirect('teacher_classroom_dashboard', classroom_id=classroom.id)

@login_required(login_url='/login/')
def reject_join_request(request, classroom_id, membership_id):
    classroom = get_object_or_404(Classroom, id=classroom_id)

    if classroom.teacher != request.user and not request.user.is_superuser:
        return HttpResponseForbidden("You can manage only your own classrooms.")

    membership = get_object_or_404(
        ClassroomMembership,
        id=membership_id,
        classroom=classroom,
        role='student'
    )

    membership.status = 'rejected'
    membership.approved_at = None
    membership.save()

    messages.info(request, f"{membership.user.username}'s request was rejected.")
    return redirect('teacher_classroom_dashboard', classroom_id=classroom.id)

def classroom_access_denied(request, classroom=None, message="You do not have access to this classroom."):
    return render(request, 'sat/classroom_access_denied.html', {
        'classroom': classroom,
        'message': message,
    }, status=403)

@login_required(login_url='/login/')
def student_classroom_home(request, classroom_id):
    classroom, role, membership, redirect_response = resolve_classroom_and_role(request, classroom_id)

    if redirect_response:
        return redirect_response

    if role in ['teacher', 'admin']:
        return redirect('teacher_classroom_dashboard', classroom_id=classroom.id)

    if role != 'student':
        return classroom_access_denied(
            request,
            classroom=classroom,
            message="You do not have access to this classroom."
        )

    if not classroom.is_active:
        messages.error(request, "This classroom is no longer active.")
        return redirect('sat_menu')

    access_map = get_membership_section_access_map(membership)

    return render(request, 'sat/student_classroom_home.html', {
        'classroom': classroom,
        'membership': membership,
        'access_map': access_map,
    })

def get_membership_section_access_map(membership):
    result = {
        'practice_tests': False,
        'vocabulary': False,
        'admissions': False,
    }

    for item in membership.section_access.all():
        result[item.section] = item.has_access

    return result

@login_required(login_url='/login/')
def update_student_section_access(request, classroom_id, user_id):
    classroom = get_object_or_404(Classroom, id=classroom_id)

    if classroom.teacher != request.user and not request.user.is_superuser:
        return HttpResponseForbidden("You can manage only your own classrooms.")

    membership = get_object_or_404(
        ClassroomMembership.objects.select_related('user', 'classroom'),
        classroom=classroom,
        user_id=user_id,
        role='student',
        status='approved'
    )

    if request.method == 'POST':
        selected_sections = request.POST.getlist('sections')

        all_sections = ['practice_tests', 'vocabulary', 'admissions']

        for section in all_sections:
            access_obj, _ = StudentSectionAccess.objects.get_or_create(
                membership=membership,
                section=section,
                defaults={'has_access': False}
            )
            access_obj.has_access = section in selected_sections
            access_obj.save()

        messages.success(request, f"Access updated for {membership.user.username}.")
        return redirect('teacher_classroom_dashboard', classroom_id=classroom.id)

    access_map = get_membership_section_access_map(membership)

    return render(request, 'sat/update_student_section_access.html', {
        'classroom': classroom,
        'membership': membership,
        'access_map': access_map,
    })

@login_required(login_url='/login/')
def update_classroom_section_access(request, classroom_id):
    """Set section access for ALL approved students in the classroom at once."""
    classroom = get_object_or_404(Classroom, id=classroom_id)

    if classroom.teacher != request.user and not request.user.is_superuser:
        return HttpResponseForbidden("You can manage only your own classrooms.")

    memberships = list(
        ClassroomMembership.objects.filter(
            classroom=classroom,
            role='student',
            status='approved'
        ).select_related('user').prefetch_related('section_access')
    )

    all_sections = ['practice_tests', 'vocabulary', 'admissions']

    if request.method == 'POST':
        selected_sections = request.POST.getlist('sections')
        for membership in memberships:
            for section in all_sections:
                access_obj, _ = StudentSectionAccess.objects.get_or_create(
                    membership=membership,
                    section=section,
                    defaults={'has_access': False}
                )
                access_obj.has_access = section in selected_sections
                access_obj.save()
        messages.success(request, f"Section access updated for all {len(memberships)} students.")
        return redirect('teacher_classroom_dashboard', classroom_id=classroom.id)

    # Pre-populate: a section shows as checked if more than half of students have it
    section_counts = {s: 0 for s in all_sections}
    for membership in memberships:
        amap = get_membership_section_access_map(membership)
        for section in all_sections:
            if amap.get(section):
                section_counts[section] += 1
    total = len(memberships)
    majority_access = {
        s: (section_counts[s] > total / 2) for s in all_sections
    } if total else {s: False for s in all_sections}

    return render(request, 'sat/update_classroom_section_access.html', {
        'classroom': classroom,
        'student_count': total,
        'majority_access': majority_access,
        'section_counts': section_counts,
    })


@login_required(login_url='/login/')
def classroom_vocabulary_section(request, classroom_id, slug):
    """Classroom-aware vocabulary sub-section (word_lists / flashcards)."""
    classroom, role, membership, redirect_response = resolve_classroom_and_role(request, classroom_id)

    if redirect_response:
        return redirect_response

    if role is None:
        return classroom_access_denied(
            request,
            classroom=classroom,
            message="You do not have access to this classroom."
        )

    if role == 'student':
        access_map = get_membership_section_access_map(membership)
        if not access_map.get('vocabulary'):
            return classroom_access_denied(
                request,
                classroom=classroom,
                message="You do not have access to Vocabulary."
            )

    units = VocabularyUnit.objects.filter(is_active=True).prefetch_related('words').order_by('order', 'id')

    if slug == 'word_lists':
        return render(request, 'sat/vocabulary_word_lists.html', {
            'units': units,
            'classroom': classroom,
        })

    if slug == 'flashcards':
        return render(request, 'sat/vocabulary_flashcards.html', {
            'units': units,
            'classroom': classroom,
        })

    if slug == 'practice-quiz':
        return render(request, 'sat/vocabulary_practice_quiz.html', {
            'units': units,
            'classroom': classroom,
        })

    raise Http404("Vocabulary section not found")


@login_required(login_url='/login/')
def classroom_vocabulary_practice_quiz_start(request, classroom_id):
    """Classroom-aware vocabulary practice quiz start."""
    classroom, role, membership, redirect_response = resolve_classroom_and_role(request, classroom_id)

    if redirect_response:
        return redirect_response

    if role is None:
        return classroom_access_denied(
            request,
            classroom=classroom,
            message="You do not have access to this classroom."
        )

    if role == 'student':
        access_map = get_membership_section_access_map(membership)
        if not access_map.get('vocabulary'):
            return classroom_access_denied(
                request,
                classroom=classroom,
                message="You do not have access to Vocabulary."
            )

    if request.method != 'POST':
        return redirect('classroom_vocabulary_section', classroom_id=classroom_id, slug='practice-quiz')

    selected_ids = request.POST.getlist('units')
    selected_ids = [int(x) for x in selected_ids if x.isdigit()]
    requested_count = request.POST.get('question_count')

    if not selected_ids:
        messages.error(request, "Select at least one unit.")
        return redirect('classroom_vocabulary_section', classroom_id=classroom_id, slug='practice-quiz')

    try:
        requested_count = int(requested_count)
    except (TypeError, ValueError):
        messages.error(request, "Enter a valid number of questions.")
        return redirect('classroom_vocabulary_section', classroom_id=classroom_id, slug='practice-quiz')

    selected_units = VocabularyUnit.objects.filter(
        id__in=selected_ids,
        is_active=True
    ).prefetch_related('words')

    selected_words = []
    for unit in selected_units:
        for word in unit.words.filter(is_active=True):
            selected_words.append(word)

    if len(selected_words) < 4:
        messages.error(request, "You need at least 4 words in the selected units to generate a quiz.")
        return redirect('classroom_vocabulary_section', classroom_id=classroom_id, slug='practice-quiz')

    max_available = len(selected_words)

    if requested_count < 1:
        messages.error(request, "Question count must be at least 1.")
        return redirect('classroom_vocabulary_section', classroom_id=classroom_id, slug='practice-quiz')

    if requested_count > max_available:
        messages.error(request, f"You selected {requested_count} questions, but only {max_available} words are available.")
        return redirect('classroom_vocabulary_section', classroom_id=classroom_id, slug='practice-quiz')

    random.shuffle(selected_words)
    test_words = selected_words[:requested_count]

    all_meanings_pool = [w.meaning for w in selected_words]

    questions = []
    for word_obj in test_words:
        correct_answer = word_obj.meaning

        wrong_answers = [m for m in all_meanings_pool if m != correct_answer]
        wrong_answers = list(set(wrong_answers))
        random.shuffle(wrong_answers)
        wrong_answers = wrong_answers[:3]

        if len(wrong_answers) < 3:
            continue

        choices = [correct_answer] + wrong_answers
        random.shuffle(choices)

        questions.append({
            'unit': word_obj.unit.title,
            'question': f"What is the meaning of '{word_obj.word}'?",
            'choices': choices,
            'answer': correct_answer,
            'word': word_obj.word,
        })

    if not questions:
        messages.error(request, "Could not generate quiz questions from selected words.")
        return redirect('classroom_vocabulary_section', classroom_id=classroom_id, slug='practice-quiz')

    request.session['vocab_quiz_questions'] = questions
    request.session['vocab_quiz_units'] = [u.title for u in selected_units]
    request.session['vocab_quiz_classroom_id'] = classroom_id

    return render(request, 'sat/vocabulary_practice_quiz_test.html', {
        'questions': questions,
        'selected_units': selected_units,
        'requested_count': len(questions),
        'classroom': classroom,
    })


@login_required(login_url='/login/')
def classroom_vocabulary_practice_quiz_result(request, classroom_id):
    """Classroom-aware vocabulary practice quiz result."""
    classroom, role, membership, redirect_response = resolve_classroom_and_role(request, classroom_id)

    if redirect_response:
        return redirect_response

    if role is None:
        return classroom_access_denied(
            request,
            classroom=classroom,
            message="You do not have access to this classroom."
        )

    if role == 'student':
        access_map = get_membership_section_access_map(membership)
        if not access_map.get('vocabulary'):
            return classroom_access_denied(
                request,
                classroom=classroom,
                message="You do not have access to Vocabulary."
            )

    if request.method != 'POST':
        return redirect('classroom_vocabulary_section', classroom_id=classroom_id, slug='practice-quiz')

    questions = request.session.get('vocab_quiz_questions', [])
    score = 0
    total_questions = len(questions)
    results = []

    for i, question in enumerate(questions):
        user_answer = request.POST.get(f'question_{i}')
        is_correct = user_answer == question['answer']
        if is_correct:
            score += 1

        results.append({
            'question': question['question'],
            'user_answer': user_answer,
            'correct_answer': question['answer'],
            'is_correct': is_correct,
            'unit': question['unit'],
            'word': question['word'],
        })

    percentage = (score / total_questions * 100) if total_questions > 0 else 0

    # Clear session data
    request.session.pop('vocab_quiz_questions', None)
    request.session.pop('vocab_quiz_units', None)
    request.session.pop('vocab_quiz_classroom_id', None)

    return render(request, 'sat/vocabulary_practice_quiz_result.html', {
        'results': results,
        'score': score,
        'total': total_questions,
        'total_questions': total_questions,
        'percentage': percentage,
        'selected_units': request.session.get('vocab_quiz_units', []),
        'classroom': classroom,
    })


@login_required(login_url='/login/')
def remove_student_from_classroom(request, classroom_id, user_id):
    classroom = get_object_or_404(Classroom, id=classroom_id)

    if classroom.teacher != request.user and not request.user.is_superuser:
        return HttpResponseForbidden("You can manage only your own classrooms.")

    membership = get_object_or_404(
        ClassroomMembership,
        classroom=classroom,
        user_id=user_id,
        role='student'
    )

    membership.delete()
    messages.success(request, "Student removed from classroom.")
    return redirect('teacher_classroom_dashboard', classroom_id=classroom.id)

@login_required(login_url='/login/')
def classroom_practice_tests(request, classroom_id):
    classroom, role, membership, redirect_response = resolve_classroom_and_role(request, classroom_id)

    if redirect_response:
        return redirect_response

    if role is None:
        return classroom_access_denied(
            request,
            classroom=classroom,
            message="You do not have access to this classroom."
        )

    if role in ['teacher', 'admin']:
        tests = Test.objects.all().distinct().order_by('name')
    elif role == 'student':
        access_map = get_membership_section_access_map(membership)
        if not access_map.get('practice_tests'):
            return classroom_access_denied(
                request,
                classroom=classroom,
                message="You do not have access to Practice Tests."
            )

        tests = get_student_allowed_practice_tests_queryset(membership)
    else:
        tests = Test.objects.none()

    def get_day_number(test):
        try:
            name = str(test.name).strip().lower()
            if name.startswith('day'):
                digits = ''.join(ch for ch in name if ch.isdigit())
                if digits:
                    return int(digits)
            return 999999
        except Exception:
            return 999999

    tests = sorted(tests, key=lambda t: (get_day_number(t), str(t.name)))

    context = {
        'active_tests': tests,
        'past_tests': [],
        'classroom': classroom,
        'is_teacher_view': role in ['teacher', 'admin'],
        'purchased': True,
        'active_lessons': [],
        'past_lessons': [],
        'role': role,
        'membership': membership,
        'user': request.user,
    }
    return render(request, 'sat/practice_tests.html', context)


@login_required(login_url='/login/')
def classroom_vocabulary(request, classroom_id):
    classroom, role, membership, redirect_response = resolve_classroom_and_role(request, classroom_id)

    if redirect_response:
        return redirect_response

    if role is None:
        return classroom_access_denied(
            request,
            classroom=classroom,
            message="You do not have access to this classroom."
        )

    if role == 'student':
        access_map = get_membership_section_access_map(membership)
        if not access_map.get('vocabulary'):
            return classroom_access_denied(
                request,
                classroom=classroom,
                message="You do not have access to Vocabulary."
            )

    units = VocabularyUnit.objects.filter(is_active=True).prefetch_related('words').order_by('order', 'id')

    return render(request, 'sat/vocabulary.html', {
        'units': units,
        'classroom': classroom,
    })


@login_required(login_url='/login/')
def classroom_admissions(request, classroom_id):
    classroom, role, membership, redirect_response = resolve_classroom_and_role(request, classroom_id)

    if redirect_response:
        return redirect_response

    if role is None:
        return classroom_access_denied(
            request,
            classroom=classroom,
            message="You do not have access to this classroom."
        )

    if role == 'student':
        access_map = get_membership_section_access_map(membership)
        if not access_map.get('admissions'):
            return classroom_access_denied(
                request,
                classroom=classroom,
                message="You do not have access to Admissions."
            )

    return admissions(request)

def _can_manage_classroom_progress(user, classroom):
    return classroom.teacher_id == user.id or user.is_superuser


def _get_classroom_student_membership_or_404(classroom, student_id):
    return get_object_or_404(
        ClassroomMembership.objects.select_related('user', 'classroom').prefetch_related('section_access'),
        classroom=classroom,
        user_id=student_id,
        role='student',
        status='approved'
    )


def _sort_tests_for_progress(tests):
    def key_fn(test):
        name = str(test.name).strip().lower()
        if name.startswith('day'):
            digits = ''.join(ch for ch in name if ch.isdigit())
            if digits:
                return (0, int(digits), str(test.name).lower())
        return (1, 999999, str(test.name).lower())

    return sorted(tests, key=key_fn)


def _get_membership_allowed_tests(membership):
    explicit_access = list(
        StudentPracticeTestAccess.objects.filter(
            membership=membership,
            has_access=True
        ).select_related('test')
    )

    if explicit_access:
        tests = [item.test for item in explicit_access]
    else:
        tests = list(Test.objects.all().distinct())

    return _sort_tests_for_progress(tests)


def _build_test_progress_rows(student, tests):
    rows = []
    tests = list(tests)

    if not tests:
        return rows

    test_ids = [test.pk for test in tests]

    modules = TestModule.objects.filter(user=student, test_id__in=test_ids).select_related('test').order_by('test_id', '-created_at')
    reviews = TestReview.objects.filter(user=student, test_id__in=test_ids).select_related('test').order_by('test_id', '-created_at')
    stages = TestStage.objects.filter(user=student, test_id__in=test_ids).select_related('test').order_by('test_id', '-created_at')

    latest_review_by_test = _latest_by_test_id(reviews)
    latest_stage_by_test = _latest_by_test_id(stages)

    latest_module_by_test = {}
    latest_by_slot_by_test = defaultdict(dict)

    for module in modules:
        test_id = module.test_id
        if test_id not in latest_module_by_test:
            latest_module_by_test[test_id] = module

        slot = f"{module.section}_{module.module}"
        if slot not in latest_by_slot_by_test[test_id]:
            latest_by_slot_by_test[test_id][slot] = module

    for test in tests:
        review = latest_review_by_test.get(test.pk)
        stage = latest_stage_by_test.get(test.pk)
        latest_module = latest_module_by_test.get(test.pk)
        latest_by_slot = latest_by_slot_by_test.get(test.pk, {})

        answered_questions = 0
        for module in latest_by_slot.values():
            answered_questions += len(_safe_answers_list(module.answers))

        if review and review.score is not None:
            status = 'completed'
        elif latest_module or stage:
            status = 'in_progress'
        else:
            status = 'not_started'

        rows.append({
            'test': test,
            'status': status,
            'score': review.score if review and review.score is not None else None,
            'review_key': review.key if review and review.score is not None else '',
            'can_open_review': bool(review and review.key and review.score is not None),
            'last_activity_at': latest_module.created_at if latest_module else (review.created_at if review else None),
            'answered_questions': answered_questions,
            'has_stage': bool(stage),
            'stage_value': stage.stage if stage else None,
        })

    return rows


def _build_test_results_context_for_user(test_obj, user):
    test_mode = get_test_mode(test_obj)
    has_english = test_mode in ['full', 'ebrw_only']
    has_math = test_mode in ['full', 'math_only']

    questions = {
        'english': {'m1': [], 'm2': []},
        'math': {'m1': [], 'm2': []}
    }

    correct_counts = {
        'english': {'m1': 0, 'm2': 0},
        'math': {'m1': 0, 'm2': 0}
    }

    time_spent_totals = {
        'english': {'m1': 0, 'm2': 0},
        'math': {'m1': 0, 'm2': 0}
    }

    status = {
        'english': False,
        'math': False,
        'total': False
    }

    required_modules = []
    if has_english:
        required_modules.extend([('english', 'm1'), ('english', 'm2')])
    if has_math:
        required_modules.extend([('math', 'm1'), ('math', 'm2')])

    attempt_id = _resolve_attempt_id(user, test_obj)
    latest_modules = _load_latest_modules(user, test_obj, attempt_id=attempt_id)

    missing_modules = []
    for section, module in required_modules:
        key = f"{section}_{module}"
        if key not in latest_modules:
            missing_modules.append(key)

    if not missing_modules:
        status['total'] = True
    if has_english and 'english_m1' not in missing_modules and 'english_m2' not in missing_modules:
        status['english'] = True
    if has_math and 'math_m1' not in missing_modules and 'math_m2' not in missing_modules:
        status['math'] = True

    if missing_modules:
        return {
            'is_complete': False,
            'missing_modules': missing_modules,
            'status': status,
            'test_mode': test_mode,
            'has_english': has_english,
            'has_math': has_math,
            'questions': questions,
        }

    modules_to_process = []
    for section, module in required_modules:
        key = f"{section}_{module}"
        module_obj = latest_modules.get(key)
        if module_obj:
            modules_to_process.append(module_obj)

    english_question_map, math_question_map = _build_question_maps(modules_to_process)

    for module in modules_to_process:
        answers_list = _safe_answers_list(module.answers)

        sec = module.section
        mod = module.module

        if sec not in ['english', 'math'] or mod not in ['m1', 'm2']:
            continue

        for answer in answers_list:
            try:
                time_spent = int(answer.get('time_spent', 0) or 0)
                time_spent_totals[sec][mod] += time_spent

                question_id = int(answer['questionID'])
                if sec == 'english':
                    q_obj = english_question_map.get(question_id)
                    is_correct = bool(q_obj and answer.get('answer') == q_obj.answer)
                    display_answer = answer.get('answer')
                else:
                    q_obj = math_question_map.get(question_id)
                    raw_answer = answer.get('answer')
                    is_correct = bool(q_obj and raw_answer is not None and check_written(raw_answer, q_obj.answer))
                    display_answer = raw_answer.replace('/', '-') if raw_answer else raw_answer

                if not q_obj:
                    continue

                if is_correct:
                    correct_counts[sec][mod] += 1

                questions[sec][mod].append({
                    'id': answer['questionID'],
                    'status': 'correct' if is_correct else 'incorrect',
                    'answer': display_answer,
                    'number': q_obj.number,
                    'time_spent': time_spent
                })
            except Exception:
                continue

    if test_mode == 'full':
        score = calculator.get_total(
            correct_counts['english']['m1'],
            correct_counts['english']['m2'],
            correct_counts['math']['m1'],
            correct_counts['math']['m2']
        )
    elif test_mode == 'ebrw_only':
        english_score = correct_counts['english']['m1'] + correct_counts['english']['m2']
        score = {
            'total': english_score,
            'sections': {
                'english': {'score': english_score, 'range': {'lower': 0, 'upper': english_score}},
                'math': None,
            }
        }
    elif test_mode == 'math_only':
        math_score = correct_counts['math']['m1'] + correct_counts['math']['m2']
        score = {
            'total': math_score,
            'sections': {
                'english': None,
                'math': {'score': math_score, 'range': {'lower': 0, 'upper': math_score}},
            }
        }
    else:
        score = {
            'total': 0,
            'sections': {
                'english': None,
                'math': None,
            }
        }

    testreview = TestReview.objects.filter(
        user=user,
        test=test_obj,
        score__isnull=False
    ).order_by('-created_at').first()

    english_total_correct = correct_counts['english']['m1'] + correct_counts['english']['m2']
    math_total_correct = correct_counts['math']['m1'] + correct_counts['math']['m2']

    english_total_time = time_spent_totals['english']['m1'] + time_spent_totals['english']['m2']
    math_total_time = time_spent_totals['math']['m1'] + time_spent_totals['math']['m2']

    total_correct = english_total_correct + math_total_correct

    stats = {
        'total': total_correct,
        'test': test_obj.name,
        'english_time': english_total_time,
        'math_time': math_total_time,
        'time_spent': english_total_time + math_total_time,
    }

    return {
        'is_complete': True,
        'status': status,
        'score': score,
        'stats': stats,
        'questions': questions,
        'testreview': testreview,
        'test_mode': test_mode,
        'has_english': has_english,
        'has_math': has_math,
    }


def recalculate_practice_tests_progress(classroom, student):
    membership = ClassroomMembership.objects.filter(
        classroom=classroom,
        user=student,
        role='student',
        status='approved'
    ).first()

    if not membership:
        return

    total_items = Test.objects.count()
    completed_items = TestReview.objects.filter(user=student).exclude(score__isnull=True).count()
    activity_count = TestModule.objects.filter(user=student).count()
    last_module = TestModule.objects.filter(user=student).order_by('-created_at').first()
    last_activity_at = last_module.created_at if last_module else None

    completion_percent = 0
    if total_items > 0:
        completion_percent = round((completed_items / total_items) * 100, 2)

    StudentProgress.objects.update_or_create(
        classroom=classroom,
        student=student,
        section='practice_tests',
        defaults={
            'completion_percent': completion_percent,
            'completed_items': completed_items,
            'total_items': total_items,
            'activity_count': activity_count,
            'last_activity_at': last_activity_at,
        }
    )

def recalculate_vocabulary_progress(classroom, student):
    membership = ClassroomMembership.objects.filter(
        classroom=classroom,
        user=student,
        role='student',
        status='approved'
    ).first()

    if not membership:
        return

    total_items = VocabularyUnit.objects.count()

    # Временная логика: completed_items = 0, пока нет отдельной completion-модели
    completed_items = 0
    activity_count = 0
    last_activity_at = None

    completion_percent = 0
    if total_items > 0:
        completion_percent = round((completed_items / total_items) * 100, 2)

    StudentProgress.objects.update_or_create(
        classroom=classroom,
        student=student,
        section='vocabulary',
        defaults={
            'completion_percent': completion_percent,
            'completed_items': completed_items,
            'total_items': total_items,
            'activity_count': activity_count,
            'last_activity_at': last_activity_at,
        }
    )

def recalculate_admissions_progress(classroom, student):
    membership = ClassroomMembership.objects.filter(
        classroom=classroom,
        user=student,
        role='student',
        status='approved'
    ).first()

    if not membership:
        return

    total_items = len(ADMISSIONS_SECTIONS) if 'ADMISSIONS_SECTIONS' in globals() else 0
    completed_items = 0
    activity_count = 0
    last_activity_at = None

    completion_percent = 0
    if total_items > 0:
        completion_percent = round((completed_items / total_items) * 100, 2)

    StudentProgress.objects.update_or_create(
        classroom=classroom,
        student=student,
        section='admissions',
        defaults={
            'completion_percent': completion_percent,
            'completed_items': completed_items,
            'total_items': total_items,
            'activity_count': activity_count,
            'last_activity_at': last_activity_at,
        }
    )

def recalculate_student_progress_for_classroom(classroom, student):
    recalculate_practice_tests_progress(classroom, student)
    recalculate_vocabulary_progress(classroom, student)
    recalculate_admissions_progress(classroom, student)

@login_required(login_url='/login/')
def classroom_progress_dashboard(request, classroom_id):
    classroom = get_object_or_404(Classroom, id=classroom_id)

    if classroom.teacher != request.user and not request.user.is_superuser:
        return HttpResponseForbidden("You can manage only your own classrooms.")

    student_memberships = ClassroomMembership.objects.filter(
        classroom=classroom,
        role='student',
        status='approved'
    ).select_related('user')

    should_refresh = request.GET.get('refresh') == '1'
    if should_refresh:
        for membership in student_memberships:
            recalculate_student_progress_for_classroom(classroom, membership.user)

    progress_records = StudentProgress.objects.filter(
        classroom=classroom
    ).select_related('student').order_by('student__username', 'section')

    grouped_progress = {}
    for record in progress_records:
        student_id = record.student.id
        if student_id not in grouped_progress:
            grouped_progress[student_id] = {
                'student': record.student,
                'practice_tests': None,
                'vocabulary': None,
                'admissions': None,
            }
        grouped_progress[student_id][record.section] = record

    return render(request, 'sat/classroom_progress_dashboard.html', {
        'classroom': classroom,
        'grouped_progress': grouped_progress.values(),
        'refreshed': should_refresh,
    })

@login_required(login_url='/login/')
def classroom_student_practice_progress(request, classroom_id, student_id):
    classroom = get_object_or_404(Classroom, id=classroom_id)

    if not _can_manage_classroom_progress(request.user, classroom):
        return HttpResponseForbidden("You can manage only your own classrooms.")

    membership = _get_classroom_student_membership_or_404(classroom, student_id)
    student = membership.user

    recalculate_student_progress_for_classroom(classroom, student)

    access_map = get_membership_section_access_map(membership)
    tests = _get_membership_allowed_tests(membership) if access_map.get('practice_tests') else []
    test_rows = _build_test_progress_rows(student, tests)
    practice_progress = StudentProgress.objects.filter(
        classroom=classroom,
        student=student,
        section='practice_tests'
    ).first()

    return render(request, 'sat/classroom_student_practice_progress.html', {
        'classroom': classroom,
        'membership': membership,
        'student_obj': student,
        'access_map': access_map,
        'practice_progress': practice_progress,
        'test_rows': test_rows,
    })


@login_required(login_url='/login/')
def classroom_student_vocab_progress(request, classroom_id, student_id):
    classroom = get_object_or_404(Classroom, id=classroom_id)

    if not _can_manage_classroom_progress(request.user, classroom):
        return HttpResponseForbidden("You can manage only your own classrooms.")

    membership = _get_classroom_student_membership_or_404(classroom, student_id)
    student = membership.user

    recalculate_student_progress_for_classroom(classroom, student)

    vocab_progress = StudentProgress.objects.filter(
        classroom=classroom,
        student=student,
        section='vocabulary'
    ).first()
    units = VocabularyUnit.objects.filter(is_active=True).prefetch_related('words').order_by('order', 'id')

    return render(request, 'sat/classroom_student_vocab_progress.html', {
        'classroom': classroom,
        'membership': membership,
        'student_obj': student,
        'access_map': get_membership_section_access_map(membership),
        'vocab_progress': vocab_progress,
        'units': units,
        'total_words': sum(unit.words.filter(is_active=True).count() for unit in units),
    })


@login_required(login_url='/login/')
def classroom_student_admission_progress(request, classroom_id, student_id):
    classroom = get_object_or_404(Classroom, id=classroom_id)

    if not _can_manage_classroom_progress(request.user, classroom):
        return HttpResponseForbidden("You can manage only your own classrooms.")

    membership = _get_classroom_student_membership_or_404(classroom, student_id)
    student = membership.user

    recalculate_student_progress_for_classroom(classroom, student)

    admission_progress = StudentProgress.objects.filter(
        classroom=classroom,
        student=student,
        section='admissions'
    ).first()

    return render(request, 'sat/classroom_student_admission_progress.html', {
        'classroom': classroom,
        'membership': membership,
        'student_obj': student,
        'access_map': get_membership_section_access_map(membership),
        'admission_progress': admission_progress,
        'admission_sections': ADMISSIONS_SECTIONS,
    })


@login_required(login_url='/login/')
def classroom_student_review_results(request, classroom_id, student_id, test_name):
    classroom = get_object_or_404(Classroom, id=classroom_id)

    if not _can_manage_classroom_progress(request.user, classroom):
        return HttpResponseForbidden("You can manage only your own classrooms.")

    membership = _get_classroom_student_membership_or_404(classroom, student_id)
    student = membership.user
    test_obj = get_object_or_404(Test, name=test_name)

    result_context = _build_test_results_context_for_user(test_obj, student)
    if not result_context.get('is_complete'):
        return HttpResponse("Student has not finished all required modules for this test.")
    
    selected_review = result_context.get('testreview')
    
    context = {
        'user': request.user,
        'display_user': student,
        'classroom': classroom,
        'review_student': student,
        'is_teacher_review': True,
        'key': selected_review.key if selected_review else '',
        'selected_review_key': selected_review.key if selected_review else '',
        'selected_review': selected_review,
        'domains': selected_review.domains if selected_review else False,
    }
    context.update(result_context)
    
    return render(request, 'test/results.html', context)


@login_required(login_url='/login/')
def classroom_student_review_question(request, classroom_id, student_id, key, section, module, id):
    classroom = get_object_or_404(Classroom, id=classroom_id)

    if not _can_manage_classroom_progress(request.user, classroom):
        return HttpResponseForbidden("You can manage only your own classrooms.")

    membership = _get_classroom_student_membership_or_404(classroom, student_id)
    student = membership.user

    group, _ = Group.objects.get_or_create(name='OFFLINE')

    review = TestReview.objects.filter(key=key).select_related('user', 'test', 'makeup_test').first()
    if not review or review.user_id != student.id:
        return HttpResponse('This review is no longer available. A new retake may already be in progress.')

    if review.score is None:
        return HttpResponse('Review is unavailable because a retake is currently in progress.')

    module_obj = TestModule.objects.filter(
        test=review.test,
        user=review.user,
        section=section,
        module=module
    ).first()

    if not module_obj:
        return HttpResponse('Review for this section is unavailable because a retake is currently in progress.')

    prev, answer, new = module_obj.find_answer(question_id=id)
    prev = reverse('classroom_student_review_question', args=[classroom.id, student.id, key, section, module, prev]) if prev else ''
    new = reverse('classroom_student_review_question', args=[classroom.id, student.id, key, section, module, new]) if new else ''

    if section == 'english':
        question = English_Question.objects.filter(id=id).first()
        if not question:
            return HttpResponse('Question is not found!')
        return render(request, 'test/review/test_eng.html', {
            'question': question,
            'answered': answer,
            'prev': prev,
            'next': new,
            'test': review.test,
            'is_teacher_review': True,
            'classroom': classroom,
            'review_student': student,
        })

    if section == 'math':
        question = Math_Question.objects.filter(id=id).first()
        if not question:
            return HttpResponse('Question is not found!')
        return render(request, 'test/review/test_math.html', {
            'question': question,
            'answered': answer,
            'prev': prev,
            'next': new,
            'test': review.test,
            'is_teacher_review': True,
            'classroom': classroom,
            'review_student': student,
        })

    return HttpResponse('Invalid section')


def get_classroom_access_for_user(user, classroom_id):
    classroom = get_object_or_404(Classroom, id=classroom_id)

    if user.is_superuser:
        return classroom, 'admin', None

    if classroom.teacher_id == user.id:
        return classroom, 'teacher', None

    membership = ClassroomMembership.objects.filter(
        classroom=classroom,
        user=user,
        role='student',
        status='approved'
    ).first()

    if membership:
        return classroom, 'student', membership

    return classroom, None, None

@login_required(login_url='/login/')
def classroom_chat(request, classroom_id):
    classroom, role, membership, redirect_response = resolve_classroom_and_role(request, classroom_id)

    if redirect_response:
        return redirect_response

    if role is None:
        return classroom_access_denied(
            request,
            classroom=classroom,
            message="You do not have access to this classroom chat."
        )

    messages_qs = ChatMessage.objects.filter(
        classroom=classroom,
        is_deleted=False
    ).select_related('sender').order_by('created_at')

    last_message = messages_qs.last()
    last_message_id = last_message.id if last_message else 0

    return render(request, 'sat/classroom_chat.html', {
        'classroom': classroom,
        'chat_messages': messages_qs,
        'role': role,
        'last_message_id': last_message_id,
    })

@login_required(login_url='/login/')
def send_classroom_message(request, classroom_id):
    if request.method != 'POST':
        return redirect('classroom_chat', classroom_id=classroom_id)

    classroom, role, membership, redirect_response = resolve_classroom_and_role(request, classroom_id)

    if redirect_response:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'ok': False, 'error': 'Classroom not found.'}, status=404)
        return redirect_response

    if role is None:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'ok': False, 'error': 'Access denied.'}, status=403)
        return classroom_access_denied(
            request,
            classroom=classroom,
            message="You do not have access to this classroom chat."
        )

    message_text = request.POST.get('message', '').strip()
    uploaded_file = request.FILES.get('file')

    if not message_text and not uploaded_file:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'ok': False, 'error': 'Message or file is required.'}, status=400)
        messages.error(request, "Message or file is required.")
        return redirect('classroom_chat', classroom_id=classroom.id)

    chat_message = ChatMessage.objects.create(
        classroom=classroom,
        sender=request.user,
        message=message_text if message_text else None,
        file=uploaded_file if uploaded_file else None,
        is_deleted=False,
    )

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        full_name = chat_message.sender.get_full_name().strip()
        display_name = full_name if full_name else chat_message.sender.username

        initials = ""
        if chat_message.sender.first_name:
            initials += chat_message.sender.first_name[:1].upper()
        if chat_message.sender.last_name:
            initials += chat_message.sender.last_name[:1].upper()
        if not initials:
            initials = chat_message.sender.username[:1].upper()

        return JsonResponse({
            'ok': True,
            'message': {
                'id': chat_message.id,
                'author': display_name,
                'initials': initials,
                'is_mine': True,
                'created_at': chat_message.created_at.strftime('%Y-%m-%d %H:%M'),
                'text': chat_message.message or '',
                'file_url': chat_message.file.url if chat_message.file else '',
                'file_name': chat_message.file.name.split('/')[-1] if chat_message.file else '',
                'delete_message_url': f'/sat/classroom/{classroom.id}/chat/message/{chat_message.id}/delete/',
                'delete_file_url': f'/sat/classroom/{classroom.id}/chat/message/{chat_message.id}/delete-file/' if chat_message.file else '',
                'role': role,
            }
        })

    return redirect('classroom_chat', classroom_id=classroom.id)

@login_required(login_url='/login/')
def delete_classroom_message(request, classroom_id, message_id):
    classroom, role, membership, redirect_response = resolve_classroom_and_role(request, classroom_id)

    if redirect_response:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'ok': False, 'error': 'Classroom not found.'}, status=404)
        return redirect_response

    if role not in ['teacher', 'admin']:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'ok': False, 'error': 'Only teacher can delete messages.'}, status=403)
        return HttpResponseForbidden("Only teacher can delete messages.")

    chat_message = get_object_or_404(
        ChatMessage,
        id=message_id,
        classroom=classroom
    )

    if chat_message.file:
        chat_message.file.delete(save=False)

    chat_message.delete()

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({
            'ok': True,
            'message_id': message_id,
            'action': 'delete_message',
        })

    messages.success(request, "Chat message deleted.")
    return redirect('classroom_chat', classroom_id=classroom.id)

@login_required(login_url='/login/')
def delete_classroom(request, classroom_id):
    classroom = get_object_or_404(Classroom, id=classroom_id)

    if classroom.teacher != request.user and not request.user.is_superuser:
        return HttpResponseForbidden("You can delete only your own classrooms.")

    if request.method != 'POST':
        return redirect('teacher_classroom_dashboard', classroom_id=classroom.id)

    classroom_name = classroom.name
    classroom.delete()

    messages.success(request, f'Classroom "{classroom_name}" was deleted.')
    return redirect('teacher_classroom_list')

@login_required(login_url='/login/')
def delete_classroom_message_file(request, classroom_id, message_id):
    classroom, role, membership, redirect_response = resolve_classroom_and_role(request, classroom_id)

    if redirect_response:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'ok': False, 'error': 'Classroom not found.'}, status=404)
        return redirect_response

    if role not in ['teacher', 'admin']:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'ok': False, 'error': 'Only teacher can delete files.'}, status=403)
        return HttpResponseForbidden("Only teacher can delete files.")

    chat_message = get_object_or_404(
        ChatMessage,
        id=message_id,
        classroom=classroom
    )

    if chat_message.file:
        chat_message.file.delete(save=False)
        chat_message.file = None
        chat_message.save()

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({
            'ok': True,
            'message_id': message_id,
            'action': 'delete_file',
        })

    messages.success(request, "File deleted from message.")
    return redirect('classroom_chat', classroom_id=classroom.id)

@login_required(login_url='/login/')
def edit_classroom(request, classroom_id):
    classroom = get_object_or_404(Classroom, id=classroom_id)

    if classroom.teacher != request.user and not request.user.is_superuser:
        return HttpResponseForbidden("You can edit only your own classrooms.")

    if request.method != 'POST':
        return redirect('teacher_classroom_dashboard', classroom_id=classroom.id)

    name = request.POST.get('name', '').strip()
    description = request.POST.get('description', '').strip()

    if not name:
        messages.error(request, "Classroom name is required.")
        return redirect('teacher_classroom_dashboard', classroom_id=classroom.id)

    classroom.name = name
    classroom.description = description
    classroom.save()

    messages.success(request, "Classroom updated successfully.")
    return redirect('teacher_classroom_dashboard', classroom_id=classroom.id)

def resolve_classroom_and_role(request, classroom_id):
    classroom = Classroom.objects.filter(id=classroom_id).first()

    if not classroom:
        messages.error(request, "This classroom does not exist anymore.")
        return None, None, None, redirect('sat_menu')

    if request.user.is_superuser:
        return classroom, 'admin', None, None

    if classroom.teacher_id == request.user.id:
        return classroom, 'teacher', None, None

    membership = ClassroomMembership.objects.filter(
        classroom=classroom,
        user=request.user,
        role='student',
        status='approved'
    ).prefetch_related('section_access').first()

    if membership:
        return classroom, 'student', membership, None

    return classroom, None, None, None

@login_required(login_url='/login/')
def fetch_classroom_messages(request, classroom_id):
    classroom, role, membership, redirect_response = resolve_classroom_and_role(request, classroom_id)

    if redirect_response:
        return JsonResponse({'ok': False, 'error': 'Classroom not found.'}, status=404)

    if role is None:
        return JsonResponse({'ok': False, 'error': 'Access denied.'}, status=403)

    last_id = request.GET.get('last_id')
    try:
        last_id = int(last_id) if last_id else 0
    except ValueError:
        last_id = 0

    messages_qs = ChatMessage.objects.filter(
        classroom=classroom,
        is_deleted=False,
        id__gt=last_id
    ).select_related('sender').order_by('id')

    result = []

    for item in messages_qs:
        full_name = item.sender.get_full_name().strip()
        display_name = full_name if full_name else item.sender.username

        initials = ""
        if item.sender.first_name:
            initials += item.sender.first_name[:1].upper()
        if item.sender.last_name:
            initials += item.sender.last_name[:1].upper()
        if not initials:
            initials = item.sender.username[:1].upper()

        result.append({
            'id': item.id,
            'author': display_name,
            'initials': initials,
            'is_mine': item.sender_id == request.user.id,
            'created_at': item.created_at.strftime('%Y-%m-%d %H:%M'),
            'text': item.message or '',
            'file_url': item.file.url if item.file else '',
            'file_name': item.file.name.split('/')[-1] if item.file else '',
            'delete_message_url': f'/sat/classroom/{classroom.id}/chat/message/{item.id}/delete/',
            'delete_file_url': f'/sat/classroom/{classroom.id}/chat/message/{item.id}/delete-file/' if item.file else '',
        })

    return JsonResponse({
        'ok': True,
        'messages': result,
    })

@login_required(login_url='/login/')
def teacher_vocabulary_units(request):
    if not is_teacher(request.user):
        return HttpResponseForbidden("Only teachers can manage vocabulary.")

    units = VocabularyUnit.objects.all().order_by('order', 'title')

    return render(request, 'sat/teacher_vocabulary_units.html', {
        'units': units,
    })


@login_required(login_url='/login/')
def create_vocabulary_unit(request):
    if not is_teacher(request.user):
        return HttpResponseForbidden("Only teachers can create vocabulary units.")

    if request.method == 'POST':
        title = request.POST.get('title', '').strip()
        order_raw = request.POST.get('order', '').strip()
        description = request.POST.get('description', '').strip()

        if not title:
            messages.error(request, "Unit title is required.")
            return redirect('create_vocabulary_unit')

        try:
            order = int(order_raw)
        except (TypeError, ValueError):
            messages.error(request, "Unit order must be a valid integer.")
            return redirect('create_vocabulary_unit')

        if VocabularyUnit.objects.filter(order=order).exists():
            messages.error(request, "A vocabulary unit with this order already exists.")
            return redirect('create_vocabulary_unit')

        unit = VocabularyUnit.objects.create(
            title=title,
            order=order,
            description=description,
        )

        messages.success(request, "Vocabulary unit created successfully.")
        return redirect('teacher_vocabulary_unit_detail', unit_id=unit.id)

    return render(request, 'sat/create_vocabulary_unit.html')


@login_required(login_url='/login/')
def teacher_vocabulary_unit_detail(request, unit_id):
    if not is_teacher(request.user):
        return HttpResponseForbidden("Only teachers can manage vocabulary.")

    unit = get_object_or_404(VocabularyUnit, id=unit_id)
    words = VocabularyWord.objects.filter(unit=unit).order_by('word')
    questions = VocabularyQuestion.objects.filter(unit=unit).order_by('id')

    return render(request, 'sat/teacher_vocabulary_unit_detail.html', {
        'unit': unit,
        'words': words,
        'questions': questions,
    })


@login_required(login_url='/login/')
def create_vocabulary_word(request, unit_id):
    if not is_teacher(request.user):
        return HttpResponseForbidden("Only teachers can add vocabulary words.")

    unit = get_object_or_404(VocabularyUnit, id=unit_id)

    if request.method == 'POST':
        word = request.POST.get('word', '').strip()
        meaning = request.POST.get('meaning', '').strip()
        example = request.POST.get('example', '').strip()

        if not word:
            messages.error(request, "Word is required.")
            return redirect('create_vocabulary_word', unit_id=unit.id)

        if not meaning:
            messages.error(request, "Meaning is required.")
            return redirect('create_vocabulary_word', unit_id=unit.id)

        VocabularyWord.objects.create(
            unit=unit,
            word=word,
            meaning=meaning,
            example=example,
        )

        messages.success(request, "Vocabulary word added successfully.")
        return redirect('teacher_vocabulary_unit_detail', unit_id=unit.id)

    return render(request, 'sat/create_vocabulary_word.html', {
        'unit': unit,
    })

def parse_bulk_vocabulary_text(raw_text):
    parsed = []
    bad_lines = []

    text = raw_text.replace('\r\n', '\n').replace('\r', '\n')

    # Склеиваем переносы из PDF: новая запись начинается только с "123. ..."
    merged_lines = []
    current = ""

    for raw_line in text.split('\n'):
        line = raw_line.strip()
        if not line:
            continue

        if re.match(r'^\d+\.\s+', line):
            if current:
                merged_lines.append(current.strip())
            current = line
        else:
            current += " " + line

    if current:
        merged_lines.append(current.strip())

    for original in merged_lines:
        line = re.sub(r'^\d+\.\s*', '', original).strip()

        parts = re.split(r'\s+[—–-]\s+', line, maxsplit=1)

        if len(parts) != 2:
            bad_lines.append(original)
            continue

        word = parts[0].strip()
        meaning = parts[1].strip()

        if not word or not meaning:
            bad_lines.append(original)
            continue

        parsed.append({
            'word': word,
            'meaning': meaning,
            'example': '',
        })

    return parsed, bad_lines


@login_required(login_url='/login/')
def bulk_import_vocabulary_words(request):
    if not is_teacher(request.user):
        return HttpResponseForbidden("Only teachers can import vocabulary words.")

    if request.method == 'POST':
        raw_text = request.POST.get('raw_text', '').strip()

        if not raw_text:
            messages.error(request, "Paste the vocabulary text first.")
            return redirect('bulk_import_vocabulary_words')

        parsed_items, bad_lines = parse_bulk_vocabulary_text(raw_text)

        if not parsed_items:
            messages.error(request, "Nothing valid was parsed. Check the text format.")
            return redirect('bulk_import_vocabulary_words')

        # Убираем дубли:
        # 1) уже существующие в базе
        # 2) повторы внутри самого вставленного текста
        existing_words = {
            w.strip().lower()
            for w in VocabularyWord.objects.values_list('word', flat=True)
        }

        cleaned_items = []
        seen_in_import = set()
        skipped_duplicates = 0

        for item in parsed_items:
            key = item['word'].strip().lower()

            if key in existing_words or key in seen_in_import:
                skipped_duplicates += 1
                continue

            cleaned_items.append(item)
            seen_in_import.add(key)

        if not cleaned_items:
            messages.warning(
                request,
                f"All parsed words were duplicates. Bad lines: {len(bad_lines)}."
            )
            request.session['bulk_vocab_bad_lines'] = bad_lines[:100]
            return redirect('bulk_import_vocabulary_words')

        with transaction.atomic():
            # Гарантируем наличие Unit 1..50
            units_by_order = {u.order: u for u in VocabularyUnit.objects.all()}

            for i in range(1, 51):
                if i not in units_by_order:
                    units_by_order[i] = VocabularyUnit.objects.create(
                        order=i,
                        title=f"Unit {i}",
                        description=f"Vocabulary Unit {i}",
                        is_active=True,
                    )

            units = [units_by_order[i] for i in range(1, 51)]

            # Сколько слов уже в каждом юните
            unit_counts = {
                row['unit']: row['count']
                for row in VocabularyWord.objects.values('unit').annotate(count=Count('id'))
            }

            to_create = []
            item_index = 0

            for unit in units:
                current_count = unit_counts.get(unit.id, 0)
                free_slots = max(0, 25 - current_count)

                while free_slots > 0 and item_index < len(cleaned_items):
                    item = cleaned_items[item_index]

                    to_create.append(
                        VocabularyWord(
                            unit=unit,
                            word=item['word'],
                            meaning=item['meaning'],
                            example=item['example'],
                            is_active=True,
                        )
                    )

                    item_index += 1
                    free_slots -= 1

                if item_index >= len(cleaned_items):
                    break

            if to_create:
                VocabularyWord.objects.bulk_create(to_create, batch_size=500)

        imported_count = len(to_create)
        not_imported_count = len(cleaned_items) - imported_count

        if bad_lines:
            request.session['bulk_vocab_bad_lines'] = bad_lines[:100]
        else:
            request.session.pop('bulk_vocab_bad_lines', None)

        if not_imported_count > 0:
            messages.warning(
                request,
                f"Imported {imported_count} words. "
                f"Skipped duplicates: {skipped_duplicates}. "
                f"Unparsed lines: {len(bad_lines)}. "
                f"{not_imported_count} words were not imported because all 50 units are full."
            )
        else:
            messages.success(
                request,
                f"Imported {imported_count} words. "
                f"Skipped duplicates: {skipped_duplicates}. "
                f"Unparsed lines: {len(bad_lines)}."
            )

        return redirect('teacher_vocabulary_units')

    bad_lines = request.session.pop('bulk_vocab_bad_lines', [])
    return render(request, 'sat/bulk_import_vocabulary_words.html', {
        'bad_lines': bad_lines,
    })

@login_required(login_url='/login/')
def create_vocabulary_question(request, unit_id):
    if not is_teacher(request.user):
        return HttpResponseForbidden("Only teachers can add vocabulary questions.")

    unit = get_object_or_404(VocabularyUnit, id=unit_id)

    if request.method == 'POST':
        # Determine which content to use based on the mode
        question_rich = request.POST.get('question_rich', '').strip()
        question_latex = request.POST.get('question_latex', '').strip()

        option_a_rich = request.POST.get('option_a_rich', '').strip()
        option_a_latex = request.POST.get('option_a_latex', '').strip()

        option_b_rich = request.POST.get('option_b_rich', '').strip()
        option_b_latex = request.POST.get('option_b_latex', '').strip()

        option_c_rich = request.POST.get('option_c_rich', '').strip()
        option_c_latex = request.POST.get('option_c_latex', '').strip()

        option_d_rich = request.POST.get('option_d_rich', '').strip()
        option_d_latex = request.POST.get('option_d_latex', '').strip()

        correct_answer = request.POST.get('correct_answer', '').strip().upper()

        # Use rich text if available, otherwise use LaTeX
        question_text = question_rich or question_latex
        option_a = option_a_rich or option_a_latex
        option_b = option_b_rich or option_b_latex
        option_c = option_c_rich or option_c_latex
        option_d = option_d_rich or option_d_latex

        if not all([question_text, option_a, option_b, option_c, option_d, correct_answer]):
            messages.error(request, "All fields are required.")
            return redirect('create_vocabulary_question', unit_id=unit.id)

        if correct_answer not in ['A', 'B', 'C', 'D']:
            messages.error(request, "Correct answer must be A, B, C, or D.")
            return redirect('create_vocabulary_question', unit_id=unit.id)

        VocabularyQuestion.objects.create(
            unit=unit,
            question=question_text,
            option_a=option_a,
            option_b=option_b,
            option_c=option_c,
            option_d=option_d,
            correct_answer=correct_answer,
        )

        messages.success(request, "Vocabulary question added successfully.")
        return redirect('teacher_vocabulary_unit_detail', unit_id=unit.id)

    return render(request, 'sat/create_vocabulary_question.html', {
        'unit': unit,
    })

def get_student_allowed_practice_tests_queryset(membership):
    custom_access_items = StudentPracticeTestAccess.objects.filter(
        membership=membership,
        has_access=True
    )

    allowed_test_ids = custom_access_items.values_list('test_id', flat=True)
    return Test.objects.filter(pk__in=allowed_test_ids).distinct().order_by('name')

def get_test_mode(test):
    has_english = English_Question.objects.filter(test=test).exists()
    has_math = Math_Question.objects.filter(test=test).exists()

    if has_english and has_math:
        return 'full'
    if has_english:
        return 'ebrw_only'
    if has_math:
        return 'math_only'
    return 'empty'


def get_test_sequence(test):
    def normalize_module(module):
        if module == 'module_1':
            return 'm1'
        if module == 'module_2':
            return 'm2'
        return module

    english_modules = sorted(
        set(English_Question.objects.filter(test=test).values_list('module', flat=True)),
        key=lambda m: ['module_1', 'module_2'].index(m) if m in ['module_1', 'module_2'] else 99
    )
    math_modules = sorted(
        set(Math_Question.objects.filter(test=test).values_list('module', flat=True)),
        key=lambda m: ['module_1', 'module_2'].index(m) if m in ['module_1', 'module_2'] else 99
    )

    sequence = []
    for module in english_modules:
        sequence.append(('english', normalize_module(module)))
    for module in math_modules:
        sequence.append(('math', normalize_module(module)))
    return sequence


def get_makeup_test_sequence(makeup_test):
    def normalize_module(module):
        if module == 'module_1':
            return 'm1'
        if module == 'module_2':
            return 'm2'
        return module

    def module_sort_key(module):
        return ['module_1', 'module_2'].index(module) if module in ['module_1', 'module_2'] else 99

    english_modules = sorted(
        set(makeup_test.english_questions.values_list('module', flat=True)),
        key=module_sort_key
    )
    math_modules = sorted(
        set(makeup_test.math_questions.values_list('module', flat=True)),
        key=module_sort_key
    )

    sequence = []
    for module in english_modules:
        sequence.append(('english', normalize_module(module)))
    for module in math_modules:
        sequence.append(('math', normalize_module(module)))
    return sequence

def get_current_test_step(test_stage):
    sequence = get_test_sequence(test_stage.test)

    if not sequence:
        return None

    if test_stage.stage < 1 or test_stage.stage > len(sequence):
        return None

    return sequence[test_stage.stage - 1]


def advance_test_stage(test_stage):
    sequence = get_test_sequence(test_stage.test)

    if not sequence:
>>>>>>> d34b18b (Added AP Course)
        return True

    def resolve_section(self, section):
        """
        Section restart. Check if retakes are available before allowing.
        """
        max_retakes = self.get_max_retakes()
        
        # For unlimited retakes, max_retakes is None, so always allow
        if max_retakes is not None and self.retake_count >= max_retakes:
            self.again = False
            self.save(update_fields=['again'])
            return False

        has_english = English_Question.objects.filter(test=self.test).exists()
        has_math = Math_Question.objects.filter(test=self.test).exists()

        if has_english and has_math:
            sequence = [
                ('english', 'm1'),
                ('english', 'm2'),
                ('math', 'm1'),
                ('math', 'm2'),
            ]
        elif has_english:
            sequence = [
                ('english', 'm1'),
                ('english', 'm2'),
            ]
        elif has_math:
            sequence = [
                ('math', 'm1'),
                ('math', 'm2'),
            ]
        else:
            return False

        start_stage = None
        for index, (seq_section, seq_module) in enumerate(sequence, start=1):
            if seq_section == section:
                start_stage = index
                break

        if start_stage is None:
            return False

        self.delete_modules(section=section)
        self.invalidate_review()
        self.stage = start_stage
        self.retake_count += 1
        self.attempt_id = uuid.uuid4()
        self.save(update_fields=['stage', 'retake_count', 'attempt_id'])
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
    instance.delete_related()

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

class Classroom(models.Model):
    teacher = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='owned_classrooms'
    )
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.name} ({self.teacher.username})"


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