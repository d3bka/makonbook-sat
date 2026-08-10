from django.db import transaction

from .models import (
    ClassroomPracticeTestAccessPolicy,
    ClassroomSectionAccessPolicy,
    StudentPracticeTestAccess,
    StudentSectionAccess,
    Test,
)


@transaction.atomic
def apply_classroom_access_policy_to_membership(membership):
    """Apply stored classroom defaults when a student becomes approved.

    The function is intentionally idempotent. It only touches sections for which
    the teacher has saved a classroom-wide policy. Older classrooms without a
    policy keep their legacy per-student behavior until the teacher saves the
    class-wide access screen once (or the backfill migration can infer it).
    """
    if membership.role != 'student' or membership.status != 'approved':
        return

    policies = list(
        ClassroomSectionAccessPolicy.objects.filter(classroom=membership.classroom)
    )
    if not policies:
        return

    policy_map = {item.section: item.has_access for item in policies}

    for item in policies:
        StudentSectionAccess.objects.update_or_create(
            membership=membership,
            section=item.section,
            defaults={'has_access': item.has_access},
        )

    # SAT practice test selection is meaningful only when the section itself is on.
    if not policy_map.get('practice_tests', False):
        return

    try:
        test_policy = membership.classroom.practice_test_access_policy
    except ClassroomPracticeTestAccessPolicy.DoesNotExist:
        return

    if test_policy.access_mode == ClassroomPracticeTestAccessPolicy.ACCESS_MODE_ALL:
        test_ids = list(Test.objects.values_list('pk', flat=True))
    else:
        test_ids = list(test_policy.selected_tests.values_list('pk', flat=True))

    StudentPracticeTestAccess.objects.filter(membership=membership).delete()
    if test_ids:
        StudentPracticeTestAccess.objects.bulk_create([
            StudentPracticeTestAccess(
                membership=membership,
                test_id=test_id,
                has_access=True,
            )
            for test_id in test_ids
        ])
