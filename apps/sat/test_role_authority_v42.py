from django.contrib.auth.models import Group, User
from django.test import TestCase
from django.urls import reverse

from .models import Classroom, SupportTeacherProfile
from .roles import is_support_teacher, is_teacher


class GroupAuthoritativeRoleTests(TestCase):
    def setUp(self):
        self.teacher_group = Group.objects.create(name="Teacher")
        self.support_group = Group.objects.create(name="Support Teacher")

    def test_classroom_ownership_does_not_grant_teacher_role(self):
        user = User.objects.create_user(username="iska", password="pass12345")
        classroom = Classroom.objects.create(teacher=user, name="Legacy classroom")

        self.assertFalse(is_teacher(user))

        user.groups.add(self.teacher_group)
        self.assertTrue(is_teacher(user))

        user.groups.remove(self.teacher_group)
        self.assertFalse(is_teacher(user))

        self.client.force_login(user)
        response = self.client.get(reverse("teacher_classroom_dashboard", args=[classroom.pk]))
        self.assertEqual(response.status_code, 403)

    def test_teacher_group_revocation_is_immediate_even_when_classroom_remains(self):
        user = User.objects.create_user(username="teacher_once", password="pass12345")
        user.groups.add(self.teacher_group)
        classroom = Classroom.objects.create(teacher=user, name="Class A")

        self.client.force_login(user)
        allowed = self.client.get(reverse("teacher_classroom_dashboard", args=[classroom.pk]))
        self.assertEqual(allowed.status_code, 200)

        user.groups.clear()
        denied = self.client.get(reverse("teacher_classroom_dashboard", args=[classroom.pk]))
        self.assertEqual(denied.status_code, 403)
        self.assertTrue(Classroom.objects.filter(pk=classroom.pk).exists())

    def test_support_profile_alone_does_not_grant_support_teacher_role(self):
        user = User.objects.create_user(username="support_stale", password="pass12345")
        SupportTeacherProfile.objects.create(user=user, display_name="Support Stale", is_active=True)

        self.assertFalse(is_support_teacher(user))
        self.client.force_login(user)
        denied = self.client.get(reverse("support_teacher_planner"))
        self.assertEqual(denied.status_code, 403)

        user.groups.add(self.support_group)
        self.assertTrue(is_support_teacher(user))
