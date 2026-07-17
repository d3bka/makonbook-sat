from __future__ import annotations

import secrets
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone

from apps.sat.models import Classroom


class RatingConfig(models.Model):
    alpha = models.DecimalField(
        max_digits=4,
        decimal_places=3,
        default=Decimal("0.400"),
        validators=[MinValueValidator(Decimal("0.001")), MaxValueValidator(Decimal("1.000"))],
        help_text="Weight of the newest assessment in the monthly EWMA rating.",
    )
    min_assessments_per_classroom = models.PositiveSmallIntegerField(
        default=2,
        help_text="A classroom stream qualifies after this many assessments in the month.",
    )
    min_qualifying_classrooms = models.PositiveSmallIntegerField(
        default=2,
        help_text="Minimum qualifying classroom streams required for the public board.",
    )
    teacher_edit_window_days = models.PositiveSmallIntegerField(default=7)
    top_n = models.PositiveSmallIntegerField(default=30)
    public_board_enabled = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Rating configuration"
        verbose_name_plural = "Rating configuration"

    @classmethod
    def get_solo(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def save(self, *args, **kwargs):
        self.pk = 1
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        return None

    def __str__(self):
        return "Rating configuration"


class RatingProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="rating_profile")
    public_visible = models.BooleanField(default=True)
    parent_access_code = models.CharField(max_length=16, unique=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        if not self.parent_access_code:
            while True:
                code = secrets.token_hex(6).upper()
                if not RatingProfile.objects.filter(parent_access_code=code).exists():
                    self.parent_access_code = code
                    break
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"Rating profile: {self.user.username}"


class RatingAssessment(models.Model):
    classroom = models.ForeignKey(Classroom, on_delete=models.CASCADE, related_name="rating_assessments")
    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name="rating_assessments_received")
    teacher = models.ForeignKey(User, on_delete=models.PROTECT, related_name="rating_assessments_given")

    homework = models.DecimalField(max_digits=3, decimal_places=1, validators=[MinValueValidator(0), MaxValueValidator(10)])
    progress = models.DecimalField(max_digits=3, decimal_places=1, validators=[MinValueValidator(0), MaxValueValidator(10)])
    activity = models.DecimalField(max_digits=3, decimal_places=1, validators=[MinValueValidator(0), MaxValueValidator(10)])
    attendance = models.DecimalField(max_digits=3, decimal_places=1, validators=[MinValueValidator(0), MaxValueValidator(10)])
    behavior = models.DecimalField(max_digits=3, decimal_places=1, validators=[MinValueValidator(0), MaxValueValidator(10)])
    comment = models.CharField(max_length=500, blank=True)
    assessed_at = models.DateTimeField(default=timezone.now, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-assessed_at", "-id"]
        indexes = [
            models.Index(fields=["student", "assessed_at"], name="rating_student_date"),
            models.Index(fields=["classroom", "assessed_at"], name="rating_class_date"),
            models.Index(fields=["teacher", "assessed_at"], name="rating_teacher_date"),
        ]

    @property
    def mean_score(self):
        values = [self.homework, self.progress, self.activity, self.attendance, self.behavior]
        return sum(values, Decimal("0")) / Decimal("5")

    def clean(self):
        from django.core.exceptions import ValidationError
        from apps.sat.models import ClassroomMembership

        if self.classroom_id and self.teacher_id:
            if self.teacher_id != self.classroom.teacher_id and not (self.teacher.is_staff or self.teacher.is_superuser):
                raise ValidationError("Only the classroom owner or an administrator can assess this classroom.")
        if self.classroom_id and self.student_id:
            valid = ClassroomMembership.objects.filter(
                classroom_id=self.classroom_id,
                user_id=self.student_id,
                role="student",
                status="approved",
            ).exists()
            if not valid:
                raise ValidationError("The selected student is not an approved member of this classroom.")

    def __str__(self):
        return f"{self.student.username} - {self.classroom.name} - {self.assessed_at:%Y-%m-%d}"
