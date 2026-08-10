from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from .models import RatingProfile


class ParentLanguageV334Tests(TestCase):
    def setUp(self):
        self.url = reverse("rating_parent_lookup")

    def test_russian_language_can_be_selected_and_persists(self):
        response = self.client.get(self.url, {"lang": "ru"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Доступ для родителей")
        self.assertContains(response, "Код доступа ученика")
        self.assertEqual(self.client.session["rating_parent_language"], "ru")

        response = self.client.get(self.url)
        self.assertContains(response, "Открыть рейтинг")

    def test_uzbek_language_can_be_selected(self):
        response = self.client.get(self.url, {"lang": "uz"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ota-onalar uchun kirish")
        self.assertContains(response, "O‘quvchining kirish kodi")
        self.assertContains(response, "Reytingni ochish")

    def test_browser_language_is_used_on_first_visit(self):
        response = self.client.get(self.url, HTTP_ACCEPT_LANGUAGE="ru-RU,ru;q=0.9,en;q=0.8")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Доступ для родителей")

    def test_invalid_code_message_is_localized(self):
        response = self.client.post(self.url, {"lang": "ru", "code": "BADCODE"}, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Код не найден")

    def test_valid_code_keeps_translated_result_labels(self):
        user = User.objects.create_user(username="student_lang_test", password="x")
        profile = RatingProfile.objects.get_or_create(user=user)[0]
        profile.parent_access_code = "PARENT334"
        profile.save(update_fields=["parent_access_code"])

        response = self.client.post(self.url, {"lang": "uz", "code": "PARENT334"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "student_lang_test")
        self.assertContains(response, "Baholashlar")
        self.assertContains(response, "Sinflar")
