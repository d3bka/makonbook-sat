from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from .models import (
    Classroom,
    ClassroomMembership,
    ClassroomPracticeTestAccessPolicy,
    ClassroomSectionAccessPolicy,
    StudentPracticeTestAccess,
    StudentSectionAccess,
    Test,
)


class ClassroomAccessPolicyV333Tests(TestCase):
    def setUp(self):
        self.teacher = User.objects.create_user(username='policy_teacher', password='pass123')
        self.classroom = Classroom.objects.create(
            teacher=self.teacher,
            name='Policy Classroom',
            classroom_type=Classroom.CLASSROOM_TYPE_SAT,
        )
        self.client = Client()
        self.client.force_login(self.teacher)

    def _pending_student(self, username):
        user = User.objects.create_user(username=username, password='pass123')
        membership = ClassroomMembership.objects.create(
            classroom=self.classroom,
            user=user,
            role='student',
            status='pending',
        )
        return user, membership

    def _approve(self, membership):
        response = self.client.post(
            reverse('approve_join_request', args=[self.classroom.pk, membership.pk])
        )
        self.assertEqual(response.status_code, 302)
        membership.refresh_from_db()
        self.assertEqual(membership.status, 'approved')

    def test_teacher_can_save_section_defaults_before_any_student_joins(self):
        response = self.client.post(
            reverse('update_classroom_section_access', args=[self.classroom.pk]),
            {'sections': ['practice_tests', 'vocabulary']},
        )
        self.assertEqual(response.status_code, 302)

        policies = {
            item.section: item.has_access
            for item in ClassroomSectionAccessPolicy.objects.filter(classroom=self.classroom)
        }
        self.assertEqual(policies['practice_tests'], True)
        self.assertEqual(policies['vocabulary'], True)
        self.assertEqual(policies['admissions'], False)

        _, membership = self._pending_student('future_sections_student')
        self._approve(membership)

        access = {
            item.section: item.has_access
            for item in StudentSectionAccess.objects.filter(membership=membership)
        }
        self.assertEqual(access['practice_tests'], True)
        self.assertEqual(access['vocabulary'], True)
        self.assertEqual(access['admissions'], False)

    def test_selected_practice_tests_are_inherited_by_student_approved_later(self):
        test_a = Test.objects.create(name='POLICY DAY A')
        test_b = Test.objects.create(name='POLICY DAY B')

        self.client.post(
            reverse('update_classroom_section_access', args=[self.classroom.pk]),
            {'sections': ['practice_tests']},
        )
        response = self.client.post(
            reverse('update_classroom_practice_test_access', args=[self.classroom.pk]),
            {'access_mode': 'selected', 'tests': [str(test_b.pk)]},
        )
        self.assertEqual(response.status_code, 302)

        policy = ClassroomPracticeTestAccessPolicy.objects.get(classroom=self.classroom)
        self.assertEqual(policy.access_mode, 'selected')
        self.assertEqual(list(policy.selected_tests.values_list('pk', flat=True)), [test_b.pk])

        _, membership = self._pending_student('future_selected_student')
        self._approve(membership)

        allowed_ids = set(
            StudentPracticeTestAccess.objects.filter(
                membership=membership,
                has_access=True,
            ).values_list('test_id', flat=True)
        )
        self.assertEqual(allowed_ids, {test_b.pk})
        self.assertNotIn(test_a.pk, allowed_ids)

    def test_all_mode_includes_tests_that_exist_when_future_student_is_approved(self):
        first_test = Test.objects.create(name='POLICY ALL 1')

        self.client.post(
            reverse('update_classroom_section_access', args=[self.classroom.pk]),
            {'sections': ['practice_tests']},
        )
        response = self.client.post(
            reverse('update_classroom_practice_test_access', args=[self.classroom.pk]),
            {'access_mode': 'all'},
        )
        self.assertEqual(response.status_code, 302)

        # Created after the teacher selected "all", but before this student joins.
        later_test = Test.objects.create(name='POLICY ALL 2')

        _, membership = self._pending_student('future_all_student')
        self._approve(membership)

        allowed_ids = set(
            StudentPracticeTestAccess.objects.filter(
                membership=membership,
                has_access=True,
            ).values_list('test_id', flat=True)
        )
        self.assertIn(first_test.pk, allowed_ids)
        self.assertIn(later_test.pk, allowed_ids)


    def test_enabling_practice_section_later_applies_preconfigured_test_policy(self):
        test_obj = Test.objects.create(name='PRECONFIGURED POLICY TEST')

        # Teacher can define the test list before there are eligible students.
        response = self.client.post(
            reverse('update_classroom_practice_test_access', args=[self.classroom.pk]),
            {'access_mode': 'selected', 'tests': [str(test_obj.pk)]},
        )
        self.assertEqual(response.status_code, 302)

        student = User.objects.create_user(username='late_enable_student', password='pass123')
        membership = ClassroomMembership.objects.create(
            classroom=self.classroom,
            user=student,
            role='student',
            status='approved',
        )
        self.assertFalse(StudentPracticeTestAccess.objects.filter(membership=membership).exists())

        response = self.client.post(
            reverse('update_classroom_section_access', args=[self.classroom.pk]),
            {'sections': ['practice_tests']},
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(StudentPracticeTestAccess.objects.filter(
            membership=membership,
            test=test_obj,
            has_access=True,
        ).exists())

    def test_classwide_change_still_updates_current_students(self):
        student = User.objects.create_user(username='current_policy_student', password='pass123')
        membership = ClassroomMembership.objects.create(
            classroom=self.classroom,
            user=student,
            role='student',
            status='approved',
        )

        response = self.client.post(
            reverse('update_classroom_section_access', args=[self.classroom.pk]),
            {'sections': ['vocabulary', 'admissions']},
        )
        self.assertEqual(response.status_code, 302)

        self.assertTrue(StudentSectionAccess.objects.get(
            membership=membership,
            section='vocabulary',
        ).has_access)
        self.assertTrue(StudentSectionAccess.objects.get(
            membership=membership,
            section='admissions',
        ).has_access)
        self.assertFalse(StudentSectionAccess.objects.get(
            membership=membership,
            section='practice_tests',
        ).has_access)
