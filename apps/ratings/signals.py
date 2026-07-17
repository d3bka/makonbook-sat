from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import RatingProfile


@receiver(post_save, sender=User)
def ensure_rating_profile(sender, instance, **kwargs):
    RatingProfile.objects.get_or_create(user=instance)
