from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import NoReverseMatch, reverse

from .models import SupportTeacherProfile


class DashboardRemovalV26Tests(TestCase):
    def test_dashboard_route_name_no_longer_exists(self):
        with self.assertRaises(NoReverseMatch):
            reverse("dashboard")

    def test_dashboard_url_returns_404(self):
        user = User.objects.create_user(username="dashboard_removed_v26", password="pass123")
        self.client.force_login(user)
        response = self.client.get("/sat/dashboard/")
        self.assertEqual(response.status_code, 404)

    def test_authenticated_student_home_is_sat_entry(self):
        user = User.objects.create_user(username="student_home_v26", password="pass123")
        self.client.force_login(user)
        response = self.client.get("/")
        self.assertRedirects(response, reverse("sat_menu"))

    def test_support_teacher_sat_entry_opens_planner(self):
        user = User.objects.create_user(username="support_home_v26", password="pass123")
        SupportTeacherProfile.objects.create(user=user, display_name="Support V26", is_active=True)
        self.client.force_login(user)
        response = self.client.get(reverse("sat_menu"))
        self.assertRedirects(response, reverse("support_teacher_planner"))
