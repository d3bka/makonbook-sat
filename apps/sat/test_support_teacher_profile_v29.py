from datetime import time, timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import (
    Classroom,
    ClassroomMembership,
    SupportLessonBooking,
    SupportTeacherAvailability,
    SupportTeacherProfile,
    SupportTeacherReview,
)


class SupportTeacherProfileV29Tests(TestCase):
    def setUp(self):
        self.support_user = User.objects.create_user(
            username='support_v29',
            password='pass12345',
            first_name='Kamila',
            last_name='Rakhimova',
            email='kamila@example.com',
        )
        self.profile = SupportTeacherProfile.objects.create(
            user=self.support_user,
            display_name='Kamila SAT',
            subjects='SAT Math, Test Strategy',
            sat_total_score=1500,
            sat_math_score=780,
            sat_reading_writing_score=720,
            scores_verified=True,
            min_booking_notice_hours=0,
            cancellation_notice_hours=1,
            is_active=True,
        )
        self.student = User.objects.create_user(
            username='student_v29',
            password='pass12345',
            first_name='Aziz',
            last_name='Karimov',
        )
        classroom_teacher = User.objects.create_user(username='class_teacher_v29', password='pass12345')
        classroom = Classroom.objects.create(teacher=classroom_teacher, name='V29 Classroom')
        ClassroomMembership.objects.create(
            classroom=classroom,
            user=self.student,
            role='student',
            status='approved',
            approved_at=timezone.now(),
        )

    def test_support_teacher_can_open_and_edit_own_profile(self):
        self.client.force_login(self.support_user)
        response = self.client.get(reverse('support_teacher_profile_edit'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Build a profile students can trust')

        response = self.client.post(
            reverse('support_teacher_profile_edit'),
            {
                'first_name': 'Kamila',
                'last_name': 'Rakhimova',
                'email': 'kamila@example.com',
                'display_name': 'Kamila SAT Coach',
                'headline': 'SAT Math specialist',
                'subjects': 'SAT Math, Test Strategy',
                'bio': 'I help students understand hard SAT questions.',
                'education': 'BS Mathematics',
                'languages': 'English, Uzbek',
                'years_experience': 4,
                'sat_total_score': 1510,
                'sat_math_score': 790,
                'sat_reading_writing_score': 720,
                'telegram_username': '@kamila_sat',
                'meeting_link': 'https://meet.google.com/example-room',
                'booking_instructions': 'Send question screenshots before class.',
                'min_booking_notice_hours': 2,
                'cancellation_notice_hours': 3,
            },
        )
        self.assertRedirects(response, reverse('support_teacher_profile_edit'))
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.display_name, 'Kamila SAT Coach')
        self.assertEqual(self.profile.sat_total_score, 1510)
        self.assertFalse(self.profile.scores_verified)
        self.assertEqual(self.profile.clean_telegram_username, 'kamila_sat')

    def test_section_scores_can_calculate_total(self):
        self.client.force_login(self.support_user)
        response = self.client.post(
            reverse('support_teacher_profile_edit'),
            {
                'first_name': 'Kamila',
                'last_name': 'Rakhimova',
                'email': 'kamila@example.com',
                'display_name': 'Kamila SAT',
                'headline': 'SAT coach',
                'subjects': 'SAT Math',
                'bio': 'Profile bio',
                'education': '',
                'languages': 'English',
                'years_experience': 2,
                'sat_total_score': '',
                'sat_math_score': 770,
                'sat_reading_writing_score': 700,
                'telegram_username': '',
                'meeting_link': '',
                'booking_instructions': '',
                'min_booking_notice_hours': 0,
                'cancellation_notice_hours': 1,
            },
        )
        self.assertRedirects(response, reverse('support_teacher_profile_edit'))
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.sat_total_score, 1470)

    def test_regular_student_cannot_edit_support_profile(self):
        self.client.force_login(self.student)
        response = self.client.get(reverse('support_teacher_profile_edit'))
        self.assertEqual(response.status_code, 403)

    def test_support_teacher_can_manage_own_availability(self):
        self.client.force_login(self.support_user)
        tomorrow = timezone.localdate() + timedelta(days=1)
        response = self.client.post(
            reverse('support_teacher_availability_add'),
            {
                'day_of_week': tomorrow.weekday(),
                'start_time': '10:00',
                'end_time': '12:00',
                'slot_duration_minutes': 45,
                'buffer_minutes': 15,
                'note': 'Morning support',
                'is_active': 'on',
            },
        )
        self.assertRedirects(response, reverse('support_teacher_planner'))
        availability = SupportTeacherAvailability.objects.get(teacher=self.profile)
        self.assertEqual(availability.slot_duration_minutes, 45)

        response = self.client.post(
            reverse('support_teacher_availability_delete', args=[availability.pk]),
        )
        self.assertRedirects(response, reverse('support_teacher_planner'))
        self.assertFalse(SupportTeacherAvailability.objects.filter(pk=availability.pk).exists())

    def test_completed_lesson_review_is_private_from_students(self):
        booking = SupportLessonBooking.objects.create(
            teacher=self.profile,
            student=self.student,
            start_at=timezone.now() - timedelta(hours=2),
            end_at=timezone.now() - timedelta(hours=1),
            status=SupportLessonBooking.STATUS_COMPLETED,
            marked_completed_at=timezone.now() - timedelta(hours=1),
        )
        self.client.force_login(self.student)
        response = self.client.post(
            reverse('leave_support_lesson_feedback', args=[booking.pk]),
            {'rating': '5', 'feedback': 'Clear explanations and useful strategies.'},
        )
        self.assertRedirects(response, reverse('my_support_lessons'))
        review = SupportTeacherReview.objects.get(booking=booking)
        self.assertEqual(review.rating, 5)

        response = self.client.get(reverse('support_teacher_list'))
        self.assertNotContains(response, 'Clear explanations and useful strategies')
        self.assertContains(response, '1500')
        response = self.client.get(reverse('support_teacher_detail', args=[self.profile.pk]))
        self.assertNotContains(response, 'Aziz K.')
        self.assertNotContains(response, 'Clear explanations and useful strategies')

        self.client.force_login(self.support_user)
        response = self.client.get(reverse('support_teacher_detail', args=[self.profile.pk]))
        self.assertContains(response, 'Private lesson feedback')
        self.assertContains(response, 'Aziz Karimov')
        self.assertContains(response, 'Clear explanations and useful strategies')

    def test_review_not_allowed_before_teacher_completion(self):
        booking = SupportLessonBooking.objects.create(
            teacher=self.profile,
            student=self.student,
            start_at=timezone.now() - timedelta(hours=2),
            end_at=timezone.now() - timedelta(hours=1),
            status=SupportLessonBooking.STATUS_SCHEDULED,
        )
        self.client.force_login(self.student)
        response = self.client.post(
            reverse('leave_support_lesson_feedback', args=[booking.pk]),
            {'rating': '5', 'feedback': 'Should not save'},
            follow=True,
        )
        self.assertContains(response, 'Feedback is available once after a completed lesson')
        self.assertFalse(SupportTeacherReview.objects.filter(booking=booking).exists())
