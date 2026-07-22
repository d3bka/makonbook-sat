from datetime import datetime, time, timedelta

from django.contrib.auth.models import Group, User
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import (
    Classroom,
    ClassroomMembership,
    SupportLessonBooking,
    SupportTeacherAvailability,
    SupportTeacherProfile,
)
from .views import _build_support_teacher_slots


class SupportBookingV28Tests(TestCase):
    def setUp(self):
        self.teacher_user = User.objects.create_user(
            username="support_v28", password="pass12345", first_name="Amina"
        )
        self.teacher = SupportTeacherProfile.objects.create(
            user=self.teacher_user,
            display_name="Amina Support",
            subjects="SAT Math, Test Strategy",
            meeting_link="https://meet.google.com/example-room",
            min_booking_notice_hours=0,
            cancellation_notice_hours=2,
            is_active=True,
        )
        self.student = User.objects.create_user(username="student_v28", password="pass12345")
        classroom_teacher = User.objects.create_user(username="class_teacher_v28", password="pass12345")
        self.classroom = Classroom.objects.create(teacher=classroom_teacher, name="V28 SAT")
        ClassroomMembership.objects.create(
            classroom=self.classroom,
            user=self.student,
            role="student",
            status="approved",
            approved_at=timezone.now(),
        )

        tomorrow = timezone.localdate() + timedelta(days=1)
        self.tomorrow = tomorrow
        self.availability = SupportTeacherAvailability.objects.create(
            teacher=self.teacher,
            day_of_week=tomorrow.weekday(),
            start_time=time(10, 0),
            end_time=time(12, 0),
            slot_duration_minutes=45,
            buffer_minutes=15,
            is_active=True,
        )

    def _local_dt(self, day, hour, minute=0):
        return timezone.make_aware(
            datetime.combine(day, time(hour, minute)),
            timezone.get_current_timezone(),
        )

    def test_availability_window_generates_duration_and_buffer_slots(self):
        slots = _build_support_teacher_slots(self.teacher, days=2)
        tomorrow_slots = [slot for slot in slots if timezone.localdate(slot["start_at"]) == self.tomorrow]
        self.assertEqual(len(tomorrow_slots), 2)
        self.assertEqual(tomorrow_slots[0]["time_label"], "10:00 - 10:45")
        self.assertEqual(tomorrow_slots[1]["time_label"], "11:00 - 11:45")

    def test_overlapping_weekly_windows_are_rejected(self):
        overlap = SupportTeacherAvailability(
            teacher=self.teacher,
            day_of_week=self.tomorrow.weekday(),
            start_time=time(11, 30),
            end_time=time(13, 0),
            slot_duration_minutes=60,
        )
        with self.assertRaises(ValidationError):
            overlap.full_clean()

    def test_booking_copies_topic_and_default_meeting_link(self):
        self.client.force_login(self.student)
        slot = _build_support_teacher_slots(self.teacher, days=2)[0]
        response = self.client.post(
            reverse("book_support_lesson", args=[self.teacher.pk]),
            {
                "slot": slot["value"],
                "topic": SupportLessonBooking.TOPIC_MATH,
                "student_note": "Review quadratic equations",
            },
        )
        self.assertRedirects(response, reverse("my_support_lessons"))
        booking = SupportLessonBooking.objects.get(student=self.student)
        self.assertEqual(booking.topic, SupportLessonBooking.TOPIC_MATH)
        self.assertEqual(booking.meeting_link, self.teacher.meeting_link)

    def test_student_overlap_is_blocked_even_with_another_teacher(self):
        other_user = User.objects.create_user(username="support_other_v28", password="pass12345")
        other_teacher = SupportTeacherProfile.objects.create(
            user=other_user,
            display_name="Other Teacher",
            min_booking_notice_hours=0,
        )
        SupportTeacherAvailability.objects.create(
            teacher=other_teacher,
            day_of_week=self.tomorrow.weekday(),
            start_time=time(10, 15),
            end_time=time(11, 0),
            slot_duration_minutes=45,
        )
        SupportLessonBooking.objects.create(
            teacher=self.teacher,
            student=self.student,
            start_at=self._local_dt(self.tomorrow, 10, 0),
            end_at=self._local_dt(self.tomorrow, 10, 45),
        )
        self.client.force_login(self.student)
        slot = _build_support_teacher_slots(other_teacher, days=2)[0]
        response = self.client.post(
            reverse("book_support_lesson", args=[other_teacher.pk]),
            {"slot": slot["value"], "topic": SupportLessonBooking.TOPIC_GENERAL},
            follow=True,
        )
        self.assertContains(response, "already have another support lesson")
        self.assertEqual(SupportLessonBooking.objects.filter(student=self.student).count(), 1)

    def test_student_cannot_cancel_inside_notice_window(self):
        start_at = timezone.now() + timedelta(hours=1)
        booking = SupportLessonBooking.objects.create(
            teacher=self.teacher,
            student=self.student,
            start_at=start_at,
            end_at=start_at + timedelta(minutes=45),
        )
        self.client.force_login(self.student)
        response = self.client.post(
            reverse("cancel_support_lesson", args=[booking.pk]),
            {"reason": "Too late"},
            follow=True,
        )
        booking.refresh_from_db()
        self.assertEqual(booking.status, SupportLessonBooking.STATUS_SCHEDULED)
        self.assertContains(response, "Online cancellation closes")

    def test_past_lesson_waits_for_teacher_confirmation(self):
        booking = SupportLessonBooking.objects.create(
            teacher=self.teacher,
            student=self.student,
            start_at=timezone.now() - timedelta(hours=2),
            end_at=timezone.now() - timedelta(hours=1),
        )
        self.client.force_login(self.student)
        response = self.client.get(reverse("my_support_lessons"))
        booking.refresh_from_db()
        self.assertEqual(booking.status, SupportLessonBooking.STATUS_SCHEDULED)
        self.assertContains(response, "Awaiting teacher confirmation")
        self.assertFalse(booking.can_receive_feedback)

    def test_support_teacher_can_mark_no_show(self):
        booking = SupportLessonBooking.objects.create(
            teacher=self.teacher,
            student=self.student,
            start_at=timezone.now() - timedelta(hours=2),
            end_at=timezone.now() - timedelta(hours=1),
        )
        self.client.force_login(self.teacher_user)
        response = self.client.post(
            reverse("manage_support_lesson", args=[booking.pk]),
            {"action": "no_show"},
        )
        self.assertRedirects(response, reverse("support_teacher_planner"))
        booking.refresh_from_db()
        self.assertEqual(booking.status, SupportLessonBooking.STATUS_NO_SHOW)

    def test_student_cannot_manage_teacher_booking(self):
        booking = SupportLessonBooking.objects.create(
            teacher=self.teacher,
            student=self.student,
            start_at=timezone.now() + timedelta(days=1),
            end_at=timezone.now() + timedelta(days=1, hours=1),
        )
        self.client.force_login(self.student)
        response = self.client.post(
            reverse("manage_support_lesson", args=[booking.pk]),
            {"action": "complete"},
        )
        self.assertEqual(response.status_code, 403)

    def test_new_public_ui_is_rendered(self):
        self.client.force_login(self.student)
        response = self.client.get(reverse("support_teacher_list"))
        self.assertContains(response, "Book focused help with a SAT support teacher")
        self.assertContains(response, "support-booking-v29.css")
        response = self.client.get(reverse("support_teacher_detail", args=[self.teacher.pk]))
        self.assertContains(response, "Select a lesson time")
        self.assertContains(response, "Review booking")

    def test_admin_booking_dashboard(self):
        admin = User.objects.create_superuser(username="admin_v28", password="pass12345", email="admin@example.com")
        self.client.force_login(admin)
        response = self.client.get(reverse("admin_support_bookings"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Support Bookings")
