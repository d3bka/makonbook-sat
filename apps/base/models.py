from django.db import models
from django.contrib.auth.models import User
import uuid
from django.utils import timezone
from django.db.models.signals import post_save
from django.dispatch import receiver
from datetime import timedelta


def email_verification_expiry():
    return timezone.now() + timedelta(hours=24)


def password_reset_expiry():
    return timezone.now() + timedelta(minutes=10)


class EmailVerification(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    token = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    is_verified = models.BooleanField(default=False)
    expires_at = models.DateTimeField(default=email_verification_expiry)

    def __str__(self):
        return f"{self.user.username} - {self.token}"


class PasswordResetCode(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="password_reset_codes")
    email = models.EmailField()
    code_hash = models.CharField(max_length=128)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(default=password_reset_expiry)
    attempts = models.PositiveSmallIntegerField(default=0)
    is_used = models.BooleanField(default=False)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["email", "is_used", "expires_at"]),
            models.Index(fields=["user", "is_used", "created_at"]),
        ]

    def __str__(self):
        return f"Password reset for {self.email}"

    @property
    def is_expired(self):
        return timezone.now() >= self.expires_at


class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    english_time_minutes = models.PositiveIntegerField(
        default=32,
        help_text="Time limit for English section in minutes (default: 32)"
    )
    math_time_minutes = models.PositiveIntegerField(
        default=35,
        help_text="Time limit for Math section in minutes (default: 35)"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.username}'s Profile"

    def is_offline_user(self):
        return self.user.groups.filter(name="OFFLINE").exists()

    def get_english_time_seconds(self):
        return self.english_time_minutes * 60

    def get_math_time_seconds(self):
        return self.math_time_minutes * 60


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.create(user=instance)


@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    if hasattr(instance, "profile"):
        instance.profile.save()
    else:
        UserProfile.objects.get_or_create(user=instance)

class GeneralIssueReport(models.Model):
    CATEGORY_CHOICES = [
        ("technical", "Technical problem"),
        ("content", "Question or content problem"),
        ("account", "Account or access problem"),
        ("rating", "Rating problem"),
        ("suggestion", "Suggestion"),
        ("other", "Other"),
    ]
    STATUS_CHOICES = [
        ("new", "New"),
        ("reviewing", "Reviewing"),
        ("resolved", "Resolved"),
        ("rejected", "Rejected"),
    ]

    reporter = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="general_issue_reports",
    )
    reporter_name = models.CharField(max_length=160, blank=True)
    reporter_email = models.EmailField(blank=True)
    category = models.CharField(max_length=30, choices=CATEGORY_CHOICES, default="technical")
    message = models.TextField(max_length=4000)
    page_url = models.CharField(max_length=1000, blank=True)
    page_title = models.CharField(max_length=300, blank=True)
    user_agent = models.CharField(max_length=1000, blank=True)
    context_data = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="new", db_index=True)
    admin_note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["status", "created_at"], name="base_issue_status_date")]

    def __str__(self):
        return f"Issue #{self.pk} - {self.get_category_display()}"
