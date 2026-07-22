from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import Classroom, ClassroomMembership, DreamUniversity, StudentGoalProfile
from .student_goal_forms import OFFICIAL_SAT_DATES


def next_official_sat_date():
    return next(item for item in OFFICIAL_SAT_DATES if item >= timezone.localdate())


class StudentGoalDashboardV32Tests(TestCase):
    def setUp(self):
        self.teacher = User.objects.create_user(username='v32_teacher', password='pass123')
        self.student = User.objects.create_user(
            username='v32_student',
            password='pass123',
            first_name='Student',
        )
        self.classroom = Classroom.objects.create(
            teacher=self.teacher,
            name='V32 Classroom',
            description='Goal modal test classroom.',
        )
        ClassroomMembership.objects.create(
            classroom=self.classroom,
            user=self.student,
            role='student',
            status='approved',
            approved_at=timezone.now(),
        )
        self.university, _ = DreamUniversity.objects.update_or_create(
            name='Purdue University',
            country='United States',
            defaults={
                'city': 'West Lafayette',
                'average_sat_score': 1450,
                'score_note': 'Reference score maintained by MakonBook.',
                'is_active': True,
            },
        )

    def test_student_dashboard_modal_is_present_but_does_not_block_site(self):
        self.client.force_login(self.student)
        response = self.client.get(reverse('sat_menu'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Student Dashboard')
        self.assertContains(response, 'Set your dream university')
        self.assertContains(response, 'Purdue University')
        self.assertContains(response, 'Others')
        self.assertContains(response, 'data-official-sat-date-select="1"')
        self.assertContains(response, 'data-auto-open="0"')
        self.assertContains(response, 'data-goal-modal-close')
        self.assertNotContains(response, 'data-required-setup')
        self.assertNotContains(response, 'type="date"')
        self.assertTrue(StudentGoalProfile.objects.filter(user=self.student).exists())

    def test_goal_query_opens_modal_explicitly(self):
        self.client.force_login(self.student)
        response = self.client.get(f"{reverse('sat_menu')}?goal=1")
        self.assertContains(response, 'data-auto-open="1"')
        self.assertContains(response, 'aria-hidden="false"')

    def test_known_university_is_saved_through_global_ajax_endpoint(self):
        self.client.force_login(self.student)
        exam_date = next_official_sat_date()
        response = self.client.post(
            reverse('student_goal_settings'),
            {
                'university_choice': f'university:{self.university.pk}',
                'custom_university_name': 'Must be cleared',
                'custom_university_country': 'Must be cleared',
                'custom_average_sat_score': 1500,
                'target_sat_score': 1500,
                'exam_date': exam_date.isoformat(),
                'daily_study_minutes_goal': 60,
                'weekly_study_days_goal': 6,
                'next': reverse('sat_menu'),
            },
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
            HTTP_ACCEPT='application/json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertJSONEqual(
            response.content,
            {'ok': True, 'redirect_url': reverse('sat_menu')},
        )
        goal = StudentGoalProfile.objects.get(user=self.student)
        self.assertEqual(goal.dream_university, self.university)
        self.assertEqual(goal.custom_university_name, '')
        self.assertEqual(goal.custom_university_country, '')
        self.assertIsNone(goal.custom_average_sat_score)
        self.assertEqual(goal.target_sat_score, 1500)
        self.assertEqual(goal.exam_date, exam_date)

    def test_known_university_without_sat_average_can_be_saved(self):
        self.university.average_sat_score = None
        self.university.save(update_fields=['average_sat_score'])
        self.client.force_login(self.student)
        response = self.client.post(
            reverse('student_goal_settings'),
            {
                'university_choice': f'university:{self.university.pk}',
                'target_sat_score': 1200,
                'exam_date': next_official_sat_date().isoformat(),
                'daily_study_minutes_goal': 45,
                'weekly_study_days_goal': 5,
            },
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
            HTTP_ACCEPT='application/json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['ok'])

    def test_others_requires_and_saves_manual_university_data(self):
        self.client.force_login(self.student)
        response = self.client.post(
            reverse('student_goal_settings'),
            {
                'university_choice': 'other',
                'custom_university_name': 'Custom Tech University',
                'custom_university_country': 'Singapore',
                'custom_average_sat_score': 1480,
                'target_sat_score': 1510,
                'exam_date': next_official_sat_date().isoformat(),
                'daily_study_minutes_goal': 50,
                'weekly_study_days_goal': 5,
            },
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
            HTTP_ACCEPT='application/json',
        )

        self.assertEqual(response.status_code, 200)
        goal = StudentGoalProfile.objects.get(user=self.student)
        self.assertIsNone(goal.dream_university)
        self.assertEqual(goal.custom_university_name, 'Custom Tech University')
        self.assertEqual(goal.custom_university_country, 'Singapore')
        self.assertEqual(goal.custom_average_sat_score, 1480)

    def test_ajax_rejects_arbitrary_date_not_in_official_list(self):
        self.client.force_login(self.student)
        invalid_date = next_official_sat_date() + timedelta(days=1)
        response = self.client.post(
            reverse('student_goal_settings'),
            {
                'university_choice': f'university:{self.university.pk}',
                'target_sat_score': 1500,
                'exam_date': invalid_date.isoformat(),
                'daily_study_minutes_goal': 45,
                'weekly_study_days_goal': 5,
            },
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
            HTTP_ACCEPT='application/json',
        )

        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertFalse(payload['ok'])
        self.assertIn('exam_date', payload['errors'])

    def test_qs_top_200_are_seeded(self):
        self.assertEqual(
            DreamUniversity.objects.filter(
                ranking_source='QS World University Rankings',
                ranking_year=2027,
            ).count(),
            200,
        )

    def test_classroom_keeps_goal_command_center_and_closeable_modal(self):
        self.client.force_login(self.student)
        response = self.client.get(reverse('student_classroom_home', args=[self.classroom.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Student command center')
        self.assertContains(response, 'data-goal-modal-open')
        self.assertContains(response, 'data-goal-modal-close')
        self.assertContains(response, 'Set your dream university')

    def test_teacher_cannot_use_global_student_goal_endpoint(self):
        self.client.force_login(self.teacher)
        response = self.client.post(reverse('student_goal_settings'), {})
        self.assertEqual(response.status_code, 403)
