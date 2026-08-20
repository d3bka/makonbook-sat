import json
import uuid
from datetime import timedelta

from django.contrib.auth.models import Group, User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .guest_views import _event_availability
from .models import (
    Classroom, ClassroomMembership, English_Question, GlobalEvent,
    StudentPracticeTestAccess, StudentSectionAccess, Test,
)


class TestAvailabilityGateV36Tests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="student-v36", password="pass12345")
        self.test = Test.objects.create(name="DAY LOCK", is_available=False)
        English_Question.objects.create(
            test=self.test,
            module="module_1",
            number=1,
            question="Choose A.",
            a="A",
            b="B",
            c="C",
            d="D",
            answer="A",
        )
        self.client.force_login(self.user)

    def test_closed_test_cannot_open_start_page(self):
        response = self.client.get(reverse("practise", kwargs={"pk": self.test.name}))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("practice_tests"))

    def test_closed_test_cannot_open_live_module(self):
        response = self.client.get(reverse("test", kwargs={"pk": self.test.name}))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("practice_tests"))

    def test_closed_test_rejects_autosave_before_touching_stage(self):
        response = self.client.post(
            reverse("save_test_module_draft"),
            data=json.dumps({
                "test": self.test.name,
                "section": "english",
                "module": "m1",
                "attempt_id": str(uuid.uuid4()),
                "answers": [],
            }),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 423)
        self.assertTrue(response.json()["test_closed"])

    def test_closed_test_rejects_module_submission(self):
        response = self.client.post(
            reverse("check_the_answers"),
            data=json.dumps({
                "test": self.test.name,
                "section": "english",
                "module": "m1",
                "attempt_id": str(uuid.uuid4()),
                "answers": [],
            }),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 423)
        self.assertTrue(response.json()["test_closed"])


    def test_closed_test_blocks_student_inside_classroom(self):
        teacher = User.objects.create_user(username="classroom-owner-v36", password="pass12345")
        classroom = Classroom.objects.create(teacher=teacher, name="Placement Classroom")
        membership = ClassroomMembership.objects.create(
            classroom=classroom,
            user=self.user,
            role="student",
            status="approved",
            approved_at=timezone.now(),
        )
        StudentSectionAccess.objects.update_or_create(
            membership=membership,
            section="practice_tests",
            defaults={"has_access": True},
        )
        StudentPracticeTestAccess.objects.update_or_create(
            membership=membership,
            test=self.test,
            defaults={"has_access": True},
        )
        response = self.client.get(
            reverse("classroom_practise", kwargs={"classroom_id": classroom.pk, "pk": self.test.name})
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response.url,
            reverse("classroom_practice_tests", kwargs={"classroom_id": classroom.pk}),
        )

    def test_guest_event_remains_available_when_student_access_is_closed(self):
        now = timezone.now()
        event = GlobalEvent.objects.create(
            title="Placement Test event",
            slug="placement-test-event",
            test=self.test,
            start_at=now - timedelta(hours=1),
            end_at=now + timedelta(hours=1),
            status="live",
            is_public=True,
        )
        availability = _event_availability(event, now)
        self.assertEqual(availability["state"], "live")
        self.assertTrue(availability["can_start"])

    def test_closed_test_blocks_teacher(self):
        teacher = User.objects.create_user(username="teacher-v36", password="pass12345")
        teacher_group, _ = Group.objects.get_or_create(name="Teacher")
        teacher.groups.add(teacher_group)
        self.client.force_login(teacher)
        response = self.client.get(reverse("practise", kwargs={"pk": self.test.name}))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("practice_tests"))

    def test_closed_test_blocks_support_teacher(self):
        support = User.objects.create_user(username="support-v36", password="pass12345")
        support_group, _ = Group.objects.get_or_create(name="Support Teacher")
        support.groups.add(support_group)
        self.client.force_login(support)
        response = self.client.get(reverse("practise", kwargs={"pk": self.test.name}))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("practice_tests"))

    def test_closed_test_blocks_teacher_inside_classroom(self):
        teacher = User.objects.create_user(username="classroom-teacher-v36", password="pass12345")
        teacher_group, _ = Group.objects.get_or_create(name="Teacher")
        teacher.groups.add(teacher_group)
        classroom = Classroom.objects.create(teacher=teacher, name="Teacher Locked Classroom")
        self.client.force_login(teacher)

        response = self.client.get(
            reverse("classroom_practise", kwargs={"classroom_id": classroom.pk, "pk": self.test.name})
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response.url,
            reverse("classroom_practice_tests", kwargs={"classroom_id": classroom.pk}),
        )

    def test_manager_keeps_qa_access_when_test_is_closed(self):
        manager = User.objects.create_user(username="manager-qa-v36", password="pass12345")
        manager_group, _ = Group.objects.get_or_create(name="Manager")
        manager.groups.add(manager_group)
        self.client.force_login(manager)
        response = self.client.get(reverse("practise", kwargs={"pk": self.test.name}))
        self.assertNotEqual(response.status_code, 302)

    def test_manager_can_reopen_without_resetting_questions(self):
        manager = User.objects.create_user(username="manager-v36", password="pass12345")
        manager_group, _ = Group.objects.get_or_create(name="Manager")
        manager.groups.add(manager_group)
        self.client.force_login(manager)

        response = self.client.post(
            reverse("managed_test_toggle_availability", kwargs={"test_name": self.test.name}),
            {"state": "open"},
        )
        self.assertEqual(response.status_code, 302)
        self.test.refresh_from_db()
        self.assertTrue(self.test.is_available)
        self.assertEqual(English_Question.objects.filter(test=self.test).count(), 1)
    def test_manager_ajax_toggle_returns_json_without_full_page_redirect(self):
        manager = User.objects.create_user(username="manager-ajax-v36", password="pass12345")
        manager_group, _ = Group.objects.get_or_create(name="Manager")
        manager.groups.add(manager_group)
        self.client.force_login(manager)

        response = self.client.post(
            reverse("managed_test_toggle_availability", kwargs={"test_name": self.test.name}),
            {"state": "open"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            HTTP_ACCEPT="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])
        self.assertTrue(response.json()["is_available"])

    def test_admin_can_open_classroom_practice_tests_summary(self):
        admin = User.objects.create_superuser(
            username="admin-summary-v36",
            email="admin-summary@example.com",
            password="pass12345",
        )
        classroom = Classroom.objects.create(teacher=admin, name="Summary Classroom")
        self.client.force_login(admin)

        response = self.client.get(
            reverse("classroom_practice_tests", kwargs={"classroom_id": classroom.pk})
        )
        self.assertEqual(response.status_code, 200)

    def test_closed_test_is_hidden_from_classroom_listing_even_for_admin(self):
        admin = User.objects.create_superuser(
            username="admin-hidden-v36",
            email="admin-hidden@example.com",
            password="pass12345",
        )
        classroom = Classroom.objects.create(teacher=admin, name="Hidden Test Classroom")
        open_test = Test.objects.create(name="DAY OPEN", is_available=True)
        English_Question.objects.create(
            test=open_test,
            module="module_1",
            number=1,
            question="Visible question.",
            a="A",
            b="B",
            c="C",
            d="D",
            answer="A",
        )
        self.client.force_login(admin)

        response = self.client.get(
            reverse("classroom_practice_tests", kwargs={"classroom_id": classroom.pk})
        )
        self.assertEqual(response.status_code, 200)
        visible_names = {test.name for test in response.context["active_tests"]}
        visible_names.update(test.name for test in response.context["past_tests"])
        self.assertIn("DAY OPEN", visible_names)
        self.assertNotIn(self.test.name, visible_names)

