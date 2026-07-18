from pathlib import Path
import re

from django.conf import settings
from django.contrib.auth.models import User
from django.test import Client, SimpleTestCase, TestCase
from django.urls import NoReverseMatch, reverse

from .models import Classroom, ClassroomJoinCode, ClassroomMembership, SupportTeacherProfile


class ClassroomJoinCodeV25Tests(TestCase):
    def setUp(self):
        self.teacher = User.objects.create_user(
            username="join_teacher_v25",
            password="pass123",
            is_staff=True,
        )
        self.classroom = Classroom.objects.create(
            teacher=self.teacher,
            name="Join Code V25",
        )
        self.client.force_login(self.teacher)

    def test_dashboard_uses_post_form_for_join_code_generation(self):
        response = self.client.get(
            reverse("teacher_classroom_dashboard", args=[self.classroom.pk])
        )
        self.assertEqual(response.status_code, 200)
        action = reverse("generate_classroom_join_code", args=[self.classroom.pk])
        self.assertContains(response, f'action="{action}"')
        self.assertContains(response, 'method="post"')
        self.assertContains(response, "csrfmiddlewaretoken")

    def test_post_generates_and_displays_a_six_digit_code(self):
        response = self.client.post(
            reverse("generate_classroom_join_code", args=[self.classroom.pk]),
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        join_code = ClassroomJoinCode.objects.get(classroom=self.classroom)
        self.assertRegex(join_code.code, r"^\d{6}$")
        self.assertTrue(join_code.is_valid())
        self.assertContains(response, join_code.code)

    def test_get_does_not_mutate_join_code(self):
        response = self.client.get(
            reverse("generate_classroom_join_code", args=[self.classroom.pk])
        )
        self.assertEqual(response.status_code, 405)
        self.assertFalse(ClassroomJoinCode.objects.filter(classroom=self.classroom).exists())


class StudentSupportAccessV25Tests(TestCase):
    def setUp(self):
        self.teacher_user = User.objects.create_user(
            username="support_teacher_v25",
            password="pass123",
        )
        self.support_profile = SupportTeacherProfile.objects.create(
            user=self.teacher_user,
            display_name="Support Teacher",
            is_active=True,
        )
        self.classroom_owner = User.objects.create_user(
            username="classroom_owner_v25",
            password="pass123",
            is_staff=True,
        )
        self.classroom = Classroom.objects.create(
            teacher=self.classroom_owner,
            name="Access Classroom V25",
        )
        self.student = User.objects.create_user(
            username="new_student_v25",
            password="pass123",
        )
        self.client.force_login(self.student)

    def test_legacy_dashboard_named_route_is_removed(self):
        with self.assertRaises(NoReverseMatch):
            reverse("dashboard")

    def test_legacy_dashboard_url_returns_not_found(self):
        response = self.client.get("/sat/dashboard/")
        self.assertEqual(response.status_code, 404)

    def test_student_without_classroom_stays_on_canonical_classroom_entry(self):
        response = self.client.get(reverse("sat_menu"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "join", html=False)

    def test_student_without_approved_classroom_cannot_open_support_urls(self):
        list_response = self.client.get(reverse("support_teacher_list"))
        detail_response = self.client.get(
            reverse("support_teacher_detail", args=[self.support_profile.pk])
        )
        book_response = self.client.post(
            reverse("book_support_lesson", args=[self.support_profile.pk]),
            {"slot": ""},
        )

        self.assertEqual(list_response.status_code, 403)
        self.assertEqual(detail_response.status_code, 403)
        self.assertEqual(book_response.status_code, 403)
        self.assertContains(
            list_response,
            "after you join an active classroom",
            status_code=403,
        )

    def test_approved_student_can_open_support_teacher_list(self):
        ClassroomMembership.objects.create(
            classroom=self.classroom,
            user=self.student,
            role="student",
            status="approved",
        )
        response = self.client.get(reverse("support_teacher_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Support Teacher")

    def test_approved_student_sees_support_classes_on_classroom_home(self):
        ClassroomMembership.objects.create(
            classroom=self.classroom,
            user=self.student,
            role="student",
            status="approved",
        )
        response = self.client.get(
            reverse("student_classroom_home", args=[self.classroom.pk])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Book Support Classes")


class HighlighterToggleStaticV25Tests(SimpleTestCase):
    def test_highlighter_has_click_and_escape_deactivation_paths(self):
        js = (Path(settings.BASE_DIR) / "static/assets/js/test-eng.js").read_text(encoding="utf-8")
        self.assertIn("const setEnabled = (nextEnabled)", js)
        self.assertIn("setEnabled(!enabled)", js)
        self.assertIn("event.key === 'Escape'", js)
        self.assertIn("window.SATHighlighter", js)

    def test_header_and_footer_are_above_active_canvas(self):
        css = (Path(settings.BASE_DIR) / "static/assets/css/sat-test-interactions-v21.css").read_text(encoding="utf-8")
        canvas_match = re.search(
            r"body\.github-test-template-v20 #drawing-canvas\s*\{.*?z-index:\s*(\d+)",
            css,
            re.S,
        )
        controls_match = re.search(
            r"body\.github-test-template-v20 header,\s*body\.github-test-template-v20 footer\s*\{.*?z-index:\s*(\d+)",
            css,
            re.S,
        )
        self.assertIsNotNone(canvas_match)
        self.assertIsNotNone(controls_match)
        self.assertGreater(int(controls_match.group(1)), int(canvas_match.group(1)))
