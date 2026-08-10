from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from .classroom_access_policy import apply_classroom_access_policy_to_membership
from .models import ClassroomMembership


@receiver(pre_save, sender=ClassroomMembership)
def remember_previous_classroom_membership_status(sender, instance, **kwargs):
    if not instance.pk:
        instance._previous_classroom_status = None
        return

    instance._previous_classroom_status = (
        sender.objects.filter(pk=instance.pk)
        .values_list('status', flat=True)
        .first()
    )


@receiver(post_save, sender=ClassroomMembership)
def inherit_classroom_access_when_student_is_approved(sender, instance, created, **kwargs):
    if instance.role != 'student' or instance.status != 'approved':
        return

    previous_status = getattr(instance, '_previous_classroom_status', None)
    if created or previous_status != 'approved':
        apply_classroom_access_policy_to_membership(instance)
