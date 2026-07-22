from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .student_goal_forms import OFFICIAL_SAT_DATES

from .models import (
    Classroom,
    ClassroomMembership,
    DreamUniversity,
    StudentGoalProfile,
    StudentSectionAccess,
)


class StudentGoalDashboardV30Tests(TestCase):
    def setUp(self):
        self.teacher = User.objects.create_user(username='goal_teacher', password='pass123')
        self.student = User.objects.create_user(
            username='goal_student',
            password='pass123',
            first_name='Goal',
            last_name='Student',
        )
        self.outsider = User.objects.create_user(username='goal_outsider', password='pass123')
        self.classroom = Classroom.objects.create(
            teacher=self.teacher,
            name='Goal Classroom',
            description='Student goal dashboard test classroom.',
        )
        self.membership = ClassroomMembership.objects.create(
            classroom=self.classroom,
            user=self.student,
            role='student',
            status='approved',
            approved_at=timezone.now(),
        )
        StudentSectionAccess.objects.create(
            membership=self.membership,
            section='practice_tests',
            has_access=True,
        )
        StudentSectionAccess.objects.create(
            membership=self.membership,
            section='vocabulary',
            has_access=True,
        )
        StudentSectionAccess.objects.create(
            membership=self.membership,
            section='admissions',
            has_access=False,
        )
        self.university = DreamUniversity.objects.create(
            name='Makon University',
            country='Uzbekistan',
            average_sat_score=1350,
        )

    def test_dashboard_renders_goal_command_center_and_creates_profile(self):
        self.client.force_login(self.student)
        response = self.client.get(reverse('student_classroom_home', args=[self.classroom.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Student command center')
        self.assertContains(response, 'SAT exam countdown')
        self.assertContains(response, 'Live motivation')
        self.assertContains(response, 'Today’s focus')
        self.assertTrue(StudentGoalProfile.objects.filter(user=self.student).exists())

    def test_student_can_save_catalog_university_goal(self):
        self.client.force_login(self.student)
        exam_date = next(item for item in OFFICIAL_SAT_DATES if item >= timezone.localdate())
        response = self.client.post(
            reverse('student_goal_settings_legacy', args=[self.classroom.id]),
            {
                'dream_university': self.university.id,
                'custom_university_name': '',
                'custom_university_country': '',
                'custom_average_sat_score': '',
                'target_sat_score': 1420,
                'exam_date': exam_date.isoformat(),
                'daily_study_minutes_goal': 60,
                'weekly_study_days_goal': 6,
            },
        )

        self.assertRedirects(response, reverse('student_classroom_home', args=[self.classroom.id]))
        goal = StudentGoalProfile.objects.get(user=self.student)
        self.assertEqual(goal.dream_university, self.university)
        self.assertEqual(goal.university_name, 'Makon University')
        self.assertEqual(goal.average_sat_score, 1350)
        self.assertEqual(goal.target_sat_score, 1420)
        self.assertEqual(goal.exam_date, exam_date)
        self.assertEqual(goal.daily_study_minutes_goal, 60)
        self.assertEqual(goal.weekly_study_days_goal, 6)

    def test_student_can_save_custom_university_goal(self):
        self.client.force_login(self.student)
        exam_date = next(item for item in OFFICIAL_SAT_DATES if item >= timezone.localdate())
        response = self.client.post(
            reverse('student_goal_settings_legacy', args=[self.classroom.id]),
            {
                'dream_university': '',
                'custom_university_name': 'Custom Tech University',
                'custom_university_country': 'United States',
                'custom_average_sat_score': 1480,
                'target_sat_score': 1510,
                'exam_date': exam_date.isoformat(),
                'daily_study_minutes_goal': 50,
                'weekly_study_days_goal': 5,
            },
        )

        self.assertRedirects(response, reverse('student_classroom_home', args=[self.classroom.id]))
        goal = StudentGoalProfile.objects.get(user=self.student)
        self.assertIsNone(goal.dream_university)
        self.assertEqual(goal.university_name, 'Custom Tech University')
        self.assertEqual(goal.university_country, 'United States')
        self.assertEqual(goal.average_sat_score, 1480)

    def test_target_below_reference_score_is_rejected(self):
        self.client.force_login(self.student)
        response = self.client.post(
            reverse('student_goal_settings_legacy', args=[self.classroom.id]),
            {
                'dream_university': self.university.id,
                'target_sat_score': 1300,
                'exam_date': next(item for item in OFFICIAL_SAT_DATES if item >= timezone.localdate()).isoformat(),
                'daily_study_minutes_goal': 45,
                'weekly_study_days_goal': 5,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Your target should be at least the university reference score')

    def test_past_exam_date_is_rejected(self):
        self.client.force_login(self.student)
        response = self.client.post(
            reverse('student_goal_settings_legacy', args=[self.classroom.id]),
            {
                'dream_university': self.university.id,
                'target_sat_score': 1400,
                'exam_date': (timezone.localdate() - timedelta(days=1)).isoformat(),
                'daily_study_minutes_goal': 45,
                'weekly_study_days_goal': 5,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn('exam_date', response.context['form'].errors)

    def test_outsider_cannot_access_goal_settings(self):
        self.client.force_login(self.outsider)
        response = self.client.get(reverse('student_goal_settings_legacy', args=[self.classroom.id]))
        self.assertEqual(response.status_code, 403)

    def test_teacher_is_not_allowed_to_edit_student_goal(self):
        self.client.force_login(self.teacher)
        response = self.client.get(reverse('student_goal_settings_legacy', args=[self.classroom.id]))
        self.assertEqual(response.status_code, 403)
