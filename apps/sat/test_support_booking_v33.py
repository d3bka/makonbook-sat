from datetime import time, timedelta

from django.contrib.auth.models import Group, User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import (
    Classroom,
    ClassroomMembership,
    SupportLessonBooking,
    SupportLessonSession,
    SupportLessonTitle,
    SupportLessonTopic,
    SupportTeacherAvailability,
    SupportTeacherProfile,
    SupportTeacherReview,
)
from .views import _build_support_teacher_slots


class SupportBookingV33Tests(TestCase):
    def setUp(self):
        self.support_user = User.objects.create_user(
            username='support_v33', password='pass12345', first_name='Amina'
        )
        self.support_teacher = SupportTeacherProfile.objects.create(
            user=self.support_user,
            display_name='Amina Support',
            subjects='SAT Math, Test Strategy',
            meeting_link='https://meet.google.com/example-room',
            min_booking_notice_hours=0,
            cancellation_notice_hours=2,
            is_active=True,
        )
        self.classroom_teacher = User.objects.create_user(
            username='class_teacher_v33', password='pass12345'
        )
        self.classroom = Classroom.objects.create(
            teacher=self.classroom_teacher, name='V33 SAT'
        )
        self.student = self._create_student('student_v33')
        self.student2 = self._create_student('student2_v33')
        self.student3 = self._create_student('student3_v33')

        self.title = SupportLessonTitle.objects.create(
            name='V33 Math', sort_order=90, is_active=True
        )
        self.topic = SupportLessonTopic.objects.create(
            title=self.title,
            name='V33 Advanced Math',
            default_duration_minutes=45,
            default_capacity=20,
            is_active=True,
        )

        tomorrow = timezone.localdate() + timedelta(days=1)
        self.tomorrow = tomorrow
        self.availability = SupportTeacherAvailability.objects.create(
            teacher=self.support_teacher,
            day_of_week=tomorrow.weekday(),
            start_time=time(10, 0),
            end_time=time(13, 0),
            slot_duration_minutes=45,
            buffer_minutes=15,
            is_active=True,
        )

    def _create_student(self, username):
        user = User.objects.create_user(username=username, password='pass12345')
        ClassroomMembership.objects.create(
            classroom=self.classroom,
            user=user,
            role='student',
            status='approved',
            approved_at=timezone.now(),
        )
        return user

    def _request_topic(self, student):
        self.client.force_login(student)
        return self.client.post(
            reverse('book_support_lesson', args=[self.support_teacher.pk]),
            {
                'lesson_title': self.title.id,
                'lesson_topic': self.topic.id,
                'student_note': 'Review this exact topic',
            },
        )

    def test_student_requests_topic_without_choosing_time(self):
        response = self._request_topic(self.student)
        self.assertRedirects(response, reverse('my_support_lessons'))
        booking = SupportLessonBooking.objects.get(student=self.student)
        self.assertEqual(booking.status, SupportLessonBooking.STATUS_REQUESTED)
        self.assertIsNone(booking.start_at)
        self.assertIsNone(booking.end_at)
        self.assertEqual(booking.lesson_title, self.title)
        self.assertEqual(booking.lesson_topic, self.topic)

    def test_teacher_schedules_topic_and_groups_pending_students(self):
        self._request_topic(self.student)
        self._request_topic(self.student2)
        slot = _build_support_teacher_slots(
            self.support_teacher, days=2, respect_notice=False
        )[0]

        self.client.force_login(self.support_user)
        response = self.client.post(
            reverse('schedule_support_topic_session'),
            {
                'lesson_topic': self.topic.id,
                'slot': slot['value'],
                'max_students': 20,
                'meeting_link': self.support_teacher.meeting_link,
                'is_open_for_requests': 'on',
            },
        )
        self.assertRedirects(response, reverse('support_teacher_planner'))
        session = SupportLessonSession.objects.get(lesson_topic=self.topic)
        bookings = SupportLessonBooking.objects.filter(session=session).order_by('student__username')
        self.assertEqual(bookings.count(), 2)
        self.assertTrue(all(row.status == SupportLessonBooking.STATUS_SCHEDULED for row in bookings))
        self.assertTrue(all(row.start_at == session.start_at for row in bookings))

    def test_later_matching_request_auto_joins_open_session(self):
        slot = _build_support_teacher_slots(
            self.support_teacher, days=2, respect_notice=False
        )[0]
        session = SupportLessonSession.objects.create(
            teacher=self.support_teacher,
            lesson_topic=self.topic,
            start_at=slot['start_at'],
            end_at=slot['end_at'],
            meeting_link=self.support_teacher.meeting_link,
            max_students=20,
            is_open_for_requests=True,
        )
        self._request_topic(self.student3)
        booking = SupportLessonBooking.objects.get(student=self.student3)
        self.assertEqual(booking.status, SupportLessonBooking.STATUS_SCHEDULED)
        self.assertEqual(booking.session, session)

    def test_same_topic_can_run_twice_in_one_day(self):
        slots = _build_support_teacher_slots(
            self.support_teacher, days=2, respect_notice=False
        )
        self.assertGreaterEqual(len(slots), 2)
        first = SupportLessonSession.objects.create(
            teacher=self.support_teacher,
            lesson_topic=self.topic,
            start_at=slots[0]['start_at'],
            end_at=slots[0]['end_at'],
            is_open_for_requests=False,
        )
        second = SupportLessonSession.objects.create(
            teacher=self.support_teacher,
            lesson_topic=self.topic,
            start_at=slots[1]['start_at'],
            end_at=slots[1]['end_at'],
            is_open_for_requests=True,
        )
        self.assertEqual(timezone.localdate(first.start_at), timezone.localdate(second.start_at))
        self.assertNotEqual(first.start_at, second.start_at)

    def test_feedback_is_hidden_from_students_but_visible_to_teacher(self):
        start = timezone.now() - timedelta(hours=2)
        booking = SupportLessonBooking.objects.create(
            teacher=self.support_teacher,
            student=self.student,
            lesson_title=self.title,
            lesson_topic=self.topic,
            start_at=start,
            end_at=start + timedelta(minutes=45),
            status=SupportLessonBooking.STATUS_COMPLETED,
        )
        SupportTeacherReview.objects.create(
            booking=booking,
            teacher=self.support_teacher,
            student=self.student,
            rating=2,
            feedback='Private quality note that students must not see.',
        )

        self.client.force_login(self.student2)
        response = self.client.get(reverse('support_teacher_detail', args=[self.support_teacher.pk]))
        self.assertNotContains(response, 'Private quality note that students must not see.')
        self.assertNotContains(response, 'Private lesson feedback')

        self.client.force_login(self.classroom_teacher)
        response = self.client.get(reverse('support_teacher_detail', args=[self.support_teacher.pk]))
        self.assertContains(response, 'Private quality note that students must not see.')
        self.assertContains(response, 'Private lesson feedback')

    def test_manager_dashboard_is_group_scoped(self):
        manager = User.objects.create_user(username='manager_v33', password='pass12345')
        manager_group, _ = Group.objects.get_or_create(name='Manager')
        manager.groups.add(manager_group)
        self.client.force_login(manager)
        response = self.client.get(reverse('manager_dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Manager Overview')
        self.assertContains(response, self.support_teacher.name)
        self.assertContains(response, self.classroom_teacher.username)

        self.client.force_login(self.student)
        response = self.client.get(reverse('manager_dashboard'))
        self.assertEqual(response.status_code, 403)


    def test_manager_can_drill_into_teacher_and_classroom_students_read_only(self):
        manager = User.objects.create_user(username='manager_drilldown_v33', password='pass12345')
        manager_group, _ = Group.objects.get_or_create(name='Manager')
        manager.groups.add(manager_group)
        self.client.force_login(manager)

        teacher_response = self.client.get(
            reverse('manager_teacher_detail', args=[self.classroom_teacher.pk])
        )
        self.assertEqual(teacher_response.status_code, 200)
        self.assertContains(teacher_response, 'Classrooms & students')
        self.assertContains(teacher_response, self.classroom.name)
        self.assertContains(teacher_response, self.student.username)
        self.assertContains(teacher_response, 'View all students')

        classroom_response = self.client.get(
            reverse('manager_classroom_detail', args=[self.classroom.pk])
        )
        self.assertEqual(classroom_response.status_code, 200)
        self.assertContains(classroom_response, 'Approved students')
        self.assertContains(classroom_response, self.student.username)
        self.assertContains(classroom_response, self.student2.username)
        self.assertNotContains(classroom_response, 'Remove')
        self.assertNotContains(classroom_response, 'Approve</button>')

    def test_student_cannot_open_manager_teacher_or_classroom_drilldown(self):
        self.client.force_login(self.student)
        teacher_response = self.client.get(
            reverse('manager_teacher_detail', args=[self.classroom_teacher.pk])
        )
        classroom_response = self.client.get(
            reverse('manager_classroom_detail', args=[self.classroom.pk])
        )
        self.assertEqual(teacher_response.status_code, 403)
        self.assertEqual(classroom_response.status_code, 403)

    def test_requested_booking_can_be_cancelled_before_scheduling(self):
        self._request_topic(self.student)
        booking = SupportLessonBooking.objects.get(student=self.student)
        self.client.force_login(self.student)
        response = self.client.post(
            reverse('cancel_support_lesson', args=[booking.pk]),
            {'reason': 'No longer needed'},
        )
        self.assertRedirects(response, reverse('my_support_lessons'))
        booking.refresh_from_db()
        self.assertEqual(booking.status, SupportLessonBooking.STATUS_CANCELLED)


    def test_support_teacher_planner_renders_group_controls(self):
        self._request_topic(self.student)
        self.client.force_login(self.support_user)
        response = self.client.get(reverse('support_teacher_planner'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Pending topic requests')
        self.assertContains(response, 'Schedule')
        self.assertContains(response, self.topic.name)

    def test_student_my_lessons_shows_waiting_request(self):
        self._request_topic(self.student)
        self.client.force_login(self.student)
        response = self.client.get(reverse('my_support_lessons'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Waiting for teacher')
        self.assertContains(response, self.topic.name)

    def test_new_student_ui_does_not_offer_time_slot_selection(self):
        self.client.force_login(self.student)
        response = self.client.get(reverse('support_teacher_detail', args=[self.support_teacher.pk]))
        self.assertContains(response, 'Choose a title first')
        self.assertContains(response, 'Teacher plans time')
        self.assertNotContains(response, 'name="slot"')
        self.assertNotContains(response, 'Public comment')
