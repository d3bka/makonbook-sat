from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from apps.sat.models import Classroom, ClassroomMembership

from .engine import build_board, replay_stream
from .models import RatingAssessment, RatingConfig


class RatingEngineTests(TestCase):
    def setUp(self):
        self.teacher = User.objects.create_user("teacher", password="x")
        self.student = User.objects.create_user("student", first_name="Test", last_name="Student", password="x")
        self.classroom = Classroom.objects.create(teacher=self.teacher, name="SAT Group A")
        ClassroomMembership.objects.create(classroom=self.classroom, user=self.student, role="student", status="approved")
        config = RatingConfig.get_solo()
        config.min_assessments_per_classroom = 2
        config.min_qualifying_classrooms = 1
        config.save()

    def create_assessment(self, value):
        return RatingAssessment.objects.create(
            classroom=self.classroom,
            student=self.student,
            teacher=self.teacher,
            homework=value,
            progress=value,
            activity=value,
            attendance=value,
            behavior=value,
        )

    def test_ewma_weights_newer_assessment(self):
        first = self.create_assessment(Decimal("5.0"))
        second = self.create_assessment(Decimal("10.0"))
        result = replay_stream([first, second], Decimal("0.4"))
        self.assertEqual(result, Decimal("7.00"))

    def test_student_qualifies_after_minimum_assessments(self):
        self.create_assessment(Decimal("8.0"))
        self.assertEqual(build_board(), [])
        self.create_assessment(Decimal("9.0"))
        board = build_board()
        self.assertEqual(len(board), 1)
        self.assertTrue(board[0].eligible)
        self.assertEqual(board[0].masked_name, "Test S.")

    def test_non_teacher_cannot_assess_classroom(self):
        stranger = User.objects.create_user("stranger", password="x")
        self.client.force_login(stranger)
        response = self.client.get(reverse("rating_assess_student", args=[self.classroom.pk, self.student.pk]))
        self.assertEqual(response.status_code, 403)

    def test_teacher_can_open_assessment_page(self):
        self.client.force_login(self.teacher)
        response = self.client.get(reverse("rating_assess_student", args=[self.classroom.pk, self.student.pk]))
        self.assertEqual(response.status_code, 200)

    def test_parent_lookup_is_rate_limited(self):
        url = reverse("rating_parent_lookup")
        for _ in range(10):
            response = self.client.post(url, {"code": "INVALID"})
            self.assertEqual(response.status_code, 200)
        response = self.client.post(url, {"code": "INVALID"})
        self.assertEqual(response.status_code, 429)
