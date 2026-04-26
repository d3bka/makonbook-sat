import uuid

from django.conf import settings
from django.contrib.auth.models import Group
from django.db import models
from django.utils import timezone
from django.utils.text import slugify

try:
    from apps.sat.storages import PublicStorage
except Exception:  # pragma: no cover - keeps migrations/imports safe if storage config changes
    PublicStorage = None


def _public_storage():
    return PublicStorage() if PublicStorage else None


class APClass(models.Model):
    name = models.CharField(max_length=255, unique=True)
    code = models.CharField(max_length=50, blank=True, help_text="Example: AP-CALC-AB")
    description = models.TextField(blank=True)
    groups = models.ManyToManyField(Group, blank=True, related_name="ap_classes")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "AP Class"
        verbose_name_plural = "AP Classes"
        ordering = ["name"]

    def __str__(self):
        return self.name


class APMockExam(models.Model):
    STATUS_CHOICES = [
        ("draft", "Draft"),
        ("published", "Published"),
        ("archived", "Archived"),
    ]

    title = models.CharField(max_length=255)
    slug = models.SlugField(unique=True, blank=True)
    ap_class = models.ForeignKey(APClass, on_delete=models.SET_NULL, null=True, blank=True, related_name="mock_exams")
    description = models.TextField(blank=True)
    rules = models.TextField(blank=True)
    groups = models.ManyToManyField(Group, blank=True, related_name="ap_mock_exams")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="draft")

    part_a_duration_minutes = models.PositiveIntegerField(default=60, help_text="30 MCQ, no Desmos/calculator")
    part_b_duration_minutes = models.PositiveIntegerField(default=45, help_text="15 MCQ, Desmos/calculator allowed")
    frq_duration_minutes = models.PositiveIntegerField(default=30, help_text="FRQ pages shown on screen; students answer on paper")

    show_score_immediately = models.BooleanField(default=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "AP Mock Exam"
        verbose_name_plural = "AP Mock Exams"
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.title) or "ap-mock-exam"
            slug = base
            counter = 2
            while APMockExam.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base}-{counter}"
                counter += 1
            self.slug = slug
        super().save(*args, **kwargs)

    @property
    def part_a_questions_count(self):
        return self.questions.filter(part=APMultipleChoiceQuestion.PART_A).count()

    @property
    def part_b_questions_count(self):
        return self.questions.filter(part=APMultipleChoiceQuestion.PART_B).count()

    @property
    def frq_pages_count(self):
        return self.frq_pages.count()

    def __str__(self):
        return self.title


class APMultipleChoiceQuestion(models.Model):
    PART_A = "part_a"
    PART_B = "part_b"
    PART_CHOICES = [
        (PART_A, "Part A - 30 MCQ, no Desmos"),
        (PART_B, "Part B - 15 MCQ, Desmos allowed"),
    ]
    ANSWER_CHOICES = [("A", "A"), ("B", "B"), ("C", "C"), ("D", "D"), ("E", "E")]

    exam = models.ForeignKey(APMockExam, on_delete=models.CASCADE, related_name="questions")
    part = models.CharField(max_length=20, choices=PART_CHOICES, default=PART_A)
    number = models.PositiveIntegerField(help_text="Question number inside this AP part")

    image = models.ImageField("Question image", upload_to="apclasses/question_images", storage=_public_storage(), null=True, blank=True)
    passage = models.TextField("Passage", blank=True)
    question = models.TextField("Question", blank=True)

    a = models.TextField("Choice A", blank=True)
    b = models.TextField("Choice B", blank=True)
    c = models.TextField("Choice C", blank=True)
    d = models.TextField("Choice D", blank=True)
    e = models.TextField("Choice E", blank=True)

    image_a = models.ImageField("Image A", upload_to="apclasses/choice_images", storage=_public_storage(), null=True, blank=True)
    image_b = models.ImageField("Image B", upload_to="apclasses/choice_images", storage=_public_storage(), null=True, blank=True)
    image_c = models.ImageField("Image C", upload_to="apclasses/choice_images", storage=_public_storage(), null=True, blank=True)
    image_d = models.ImageField("Image D", upload_to="apclasses/choice_images", storage=_public_storage(), null=True, blank=True)
    image_e = models.ImageField("Image E", upload_to="apclasses/choice_images", storage=_public_storage(), null=True, blank=True)

    correct_answer = models.CharField(max_length=1, choices=ANSWER_CHOICES, blank=True)
    explanation = models.TextField(blank=True)
    calculator_allowed = models.BooleanField(default=False, editable=False)
    desmos_allowed = models.BooleanField(default=False, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "AP MCQ Question"
        verbose_name_plural = "AP MCQ Questions"
        ordering = ["exam", "part", "number"]
        constraints = [
            models.UniqueConstraint(fields=["exam", "part", "number"], name="unique_ap_question_number_per_part"),
        ]

    def save(self, *args, **kwargs):
        allowed = self.part == self.PART_B
        self.calculator_allowed = allowed
        self.desmos_allowed = allowed
        super().save(*args, **kwargs)

    def get_part_label_short(self):
        return "Part A" if self.part == self.PART_A else "Part B"

    def __str__(self):
        return f"{self.exam} > {self.get_part_label_short()} > #{self.number}"


class APFRQPage(models.Model):
    exam = models.ForeignKey(APMockExam, on_delete=models.CASCADE, related_name="frq_pages")
    page_number = models.PositiveIntegerField()
    title = models.CharField(max_length=255, blank=True)
    instructions = models.TextField(blank=True)
    image = models.ImageField("FRQ page image", upload_to="apclasses/frq_pages", storage=_public_storage(), null=True, blank=True)
    file = models.FileField("FRQ PDF/file", upload_to="apclasses/frq_files", storage=_public_storage(), null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "AP FRQ Page"
        verbose_name_plural = "AP FRQ Pages"
        ordering = ["exam", "page_number"]
        constraints = [
            models.UniqueConstraint(fields=["exam", "page_number"], name="unique_ap_frq_page_per_exam"),
        ]

    def __str__(self):
        return f"{self.exam} > FRQ page {self.page_number}"


class APExamEvent(models.Model):
    EVENT_STATUS_CHOICES = [
        ("draft", "Draft"),
        ("scheduled", "Scheduled"),
        ("live", "Live"),
        ("closed", "Closed"),
    ]

    title = models.CharField(max_length=255)
    slug = models.SlugField(unique=True, blank=True)
    exam = models.ForeignKey(APMockExam, on_delete=models.CASCADE, related_name="events")
    description = models.TextField(blank=True)
    rules = models.TextField(blank=True)

    access_code = models.CharField(
        "Secret code",
        max_length=50,
        blank=True,
        help_text="Optional. If filled, students must enter this code before starting the AP mock exam.",
    )
    is_public = models.BooleanField(default=True, help_text="Show this event in the AP Classes page.")
    is_global = models.BooleanField(
        default=False,
        help_text="Make this AP mock available to all students. If off, access can be limited by classrooms or exam groups.",
    )
    classrooms = models.ManyToManyField(
        'sat.Classroom',
        blank=True,
        related_name='ap_exam_events',
        db_constraint=False,
        help_text="Classrooms that can access this AP mock when it is not global.",
    )
    status = models.CharField(max_length=20, choices=EVENT_STATUS_CHOICES, default="draft")

    start_at = models.DateTimeField(null=True, blank=True)
    end_at = models.DateTimeField(null=True, blank=True)
    always_live = models.BooleanField(default=False, help_text="If checked, event is available 24/7 while status is Live")
    part_a_duration_minutes = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Optional event-specific override for Part A. Leave blank to use the mock exam default.",
    )
    part_b_duration_minutes = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Optional event-specific override for Part B. Leave blank to use the mock exam default.",
    )
    frq_duration_minutes = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Optional event-specific override for FRQ. Leave blank to use the mock exam default.",
    )

    allow_resume = models.BooleanField(default=True)
    max_attempts = models.PositiveIntegerField(default=1, help_text="Maximum attempts allowed per student/guest for this event.")
    allow_guest_attempts = models.BooleanField(default=True, help_text="Allow unauthenticated guest users to start this event.")
    show_score_immediately = models.BooleanField(default=True)
    show_leaderboard = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "AP Exam Event"
        verbose_name_plural = "AP Exam Events"
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.title) or "ap-exam-event"
            slug = base
            counter = 2
            while APExamEvent.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base}-{counter}"
                counter += 1
            self.slug = slug
        super().save(*args, **kwargs)

    @property
    def is_live_now(self):
        if self.status != "live":
            return False
        if self.always_live:
            return True
        now = timezone.now()
        return bool(self.start_at and self.end_at and self.start_at <= now <= self.end_at)

    @property
    def requires_secret_code(self):
        return bool(self.access_code)

    def is_exam_available_for_students(self):
        if self.exam.status != "published":
            return False
        ap_class = getattr(self.exam, "ap_class", None)
        if ap_class is not None and not ap_class.is_active:
            return False
        return True

    def user_can_see(self, user):
        if not self.is_public:
            return False
        if user.is_authenticated and (user.is_staff or user.is_superuser):
            return True
        if not self.is_exam_available_for_students():
            return False
        if self.is_global:
            return True
        if not user.is_authenticated:
            return False

        if self.classrooms.filter(teacher=user, is_active=True).exists():
            return True
        if self.classrooms.filter(
            memberships__user=user,
            memberships__role='student',
            memberships__status='approved',
            is_active=True,
        ).exists():
            return True

        exam_group_ids = set(self.exam.groups.values_list("id", flat=True))
        if exam_group_ids:
            user_group_ids = set(user.groups.values_list("id", flat=True))
            return bool(exam_group_ids.intersection(user_group_ids))

        return False

    def __str__(self):
        return self.title


class APExamAttempt(models.Model):
    STATUS_CHOICES = [
        ("in_progress", "In Progress"),
        ("submitted", "Submitted"),
        ("expired", "Expired"),
    ]

    event = models.ForeignKey(APExamEvent, on_delete=models.CASCADE, related_name="attempts")
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="ap_exam_attempts", null=True, blank=True)
    guest_name = models.CharField(max_length=255, blank=True)
    guest_session_key = models.CharField(max_length=64, blank=True, db_index=True)
    token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    attempt_number = models.PositiveIntegerField(default=1)
    started_at = models.DateTimeField(auto_now_add=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    last_activity_at = models.DateTimeField(null=True, blank=True)
    part_a_started_at = models.DateTimeField(null=True, blank=True)
    part_b_started_at = models.DateTimeField(null=True, blank=True)
    frq_started_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="in_progress")
    score = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    raw_score = models.IntegerField(default=0)
    total_questions = models.PositiveIntegerField(default=0)
    answered_questions = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = "AP Exam Attempt"
        verbose_name_plural = "AP Exam Attempts"
        constraints = [
            models.UniqueConstraint(
                fields=["event", "student", "attempt_number"],
                condition=models.Q(student__isnull=False),
                name="unique_ap_attempt_number_per_student_event",
            ),
        ]

    def __str__(self):
        owner = self.student if self.student_id else (self.guest_name or self.guest_session_key or "Guest")
        return f"{owner} - {self.event} - Attempt {self.attempt_number}"


class APExamAnswer(models.Model):
    attempt = models.ForeignKey(APExamAttempt, on_delete=models.CASCADE, related_name="answers")
    question = models.ForeignKey(APMultipleChoiceQuestion, on_delete=models.CASCADE, related_name="answers")
    selected_answer = models.CharField(max_length=1, blank=True)
    is_correct = models.BooleanField(default=False)
    answered_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "AP Exam Answer"
        verbose_name_plural = "AP Exam Answers"
        constraints = [
            models.UniqueConstraint(fields=["attempt", "question"], name="unique_ap_answer_per_question"),
        ]

    def save(self, *args, **kwargs):
        self.is_correct = bool(self.selected_answer and self.question.correct_answer and self.selected_answer == self.question.correct_answer)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.attempt} - {self.question}"


class APFRQSubmission(models.Model):
    attempt = models.ForeignKey(APExamAttempt, on_delete=models.CASCADE, related_name="frq_submissions")
    page_number = models.PositiveIntegerField(default=1)
    image = models.ImageField("Handwritten answer image", upload_to="apclasses/frq_submissions", storage=_public_storage(), null=True, blank=True)
    file = models.FileField("Handwritten answer file", upload_to="apclasses/frq_submissions", storage=_public_storage(), null=True, blank=True)
    teacher_comment = models.TextField(blank=True)
    score = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "AP FRQ Submission"
        verbose_name_plural = "AP FRQ Submissions"
        ordering = ["attempt", "page_number"]

    def __str__(self):
        return f"{self.attempt} - FRQ upload {self.page_number}"
