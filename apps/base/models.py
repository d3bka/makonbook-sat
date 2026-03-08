# base/models.py
from django.db import models
from django.contrib.auth.models import User
import uuid
from django.utils import timezone
from django.db.models.signals import post_save
from django.dispatch import receiver

class EmailVerification(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    token = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    is_verified = models.BooleanField(default=False)
    expires_at = models.DateTimeField(default=timezone.now() + timezone.timedelta(hours=24))  # Expires in 24 hours

    def __str__(self):
        return f"{self.user.username} - {self.token}"

class UserProfile(models.Model):
    """Extended user profile for storing test time preferences for offline users"""
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
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
        """Check if user is in OFFLINE group"""
        return self.user.groups.filter(name='OFFLINE').exists()

    def get_english_time_seconds(self):
        """Get English time in seconds for JavaScript"""
        return self.english_time_minutes * 60

    def get_math_time_seconds(self):
        """Get Math time in seconds for JavaScript"""
        return self.math_time_minutes * 60

@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    """Create UserProfile when a new User is created"""
    if created:
        UserProfile.objects.create(user=instance)

@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    """Save UserProfile when User is saved"""
    if hasattr(instance, 'profile'):
        instance.profile.save()
    else:
        # Use get_or_create to prevent duplicates
        UserProfile.objects.get_or_create(user=instance)