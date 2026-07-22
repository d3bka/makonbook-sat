from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from .models import DreamUniversity, StudentGoalProfile
from .student_goal_forms import OFFICIAL_SAT_DATES


def next_official_sat_date():
    return next(item for item in OFFICIAL_SAT_DATES if item >= timezone.localdate())


class StudentGoalDashboardV33CsrfTests(TestCase):
    def setUp(self):
        self.student = User.objects.create_user(
            username='v33_student',
            password='pass123',
        )
        self.university = DreamUniversity.objects.filter(is_active=True).order_by('sort_order', 'name').first()
        self.assertIsNotNone(self.university)

    def test_dashboard_sets_csrf_cookie_and_points_modal_to_refresh_endpoint(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.student)

        response = client.get(reverse('sat_menu'))

        self.assertEqual(response.status_code, 200)
        self.assertIn('csrftoken', response.cookies)
        self.assertContains(
            response,
            f'data-csrf-url="{reverse("student_goal_csrf")}"',
        )
        self.assertContains(response, 'class="sg-goal-modal-body"')

    def test_csrf_refresh_endpoint_returns_matching_fresh_token(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.student)

        response = client.get(
            reverse('student_goal_csrf'),
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
            HTTP_ACCEPT='application/json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['csrfToken'])
        self.assertIn('csrftoken', response.cookies)
        self.assertIn('no-store', response['Cache-Control'])

    def test_real_csrf_checked_ajax_save_succeeds(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.student)

        token_response = client.get(
            reverse('student_goal_csrf'),
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
            HTTP_ACCEPT='application/json',
        )
        csrf_token = token_response.json()['csrfToken']

        response = client.post(
            reverse('student_goal_settings'),
            {
                'csrfmiddlewaretoken': csrf_token,
                'university_choice': f'university:{self.university.pk}',
                'target_sat_score': 1500,
                'exam_date': next_official_sat_date().isoformat(),
                'daily_study_minutes_goal': 60,
                'weekly_study_days_goal': 6,
                'next': reverse('sat_menu'),
            },
            HTTP_X_CSRFTOKEN=csrf_token,
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
            HTTP_ACCEPT='application/json',
        )

        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(response.json()['ok'])
        goal = StudentGoalProfile.objects.get(user=self.student)
        self.assertEqual(goal.dream_university, self.university)
        self.assertEqual(goal.target_sat_score, 1500)
