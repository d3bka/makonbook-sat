from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse


class ProfileNameGateV338Tests(TestCase):
    def setUp(self):
        self.User = get_user_model()
        self.user = self.User.objects.create_user(
            username='nameless-user',
            email='nameless@example.com',
            password='pass12345',
            first_name='',
            last_name='',
        )
        self.client.force_login(self.user)

    def test_endpoint_requires_both_names(self):
        response = self.client.post(
            reverse('complete_profile_name'),
            {'first_name': 'Islom', 'last_name': ''},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('last_name', response.json()['errors'])

    def test_endpoint_saves_names(self):
        response = self.client.post(
            reverse('complete_profile_name'),
            {'first_name': 'Islom', 'last_name': 'Bakhtiyorov'},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, 'Islom')
        self.assertEqual(self.user.last_name, 'Bakhtiyorov')
        self.assertEqual(response.json()['full_name'], 'Islom Bakhtiyorov')


    def test_endpoint_rejects_numbers_and_symbols(self):
        bad_values = [
            ('123', 'Bakhtiyorov'),
            ('Islom596', 'Bakhtiyorov'),
            ('Islom', 'B@khtiyorov'),
            ('!!!', 'Bakhtiyorov'),
        ]
        for first_name, last_name in bad_values:
            with self.subTest(first_name=first_name, last_name=last_name):
                response = self.client.post(
                    reverse('complete_profile_name'),
                    {'first_name': first_name, 'last_name': last_name},
                    HTTP_X_REQUESTED_WITH='XMLHttpRequest',
                )
                self.assertEqual(response.status_code, 400)
                self.assertFalse(response.json()['ok'])

    def test_endpoint_rejects_too_short_and_bad_punctuation(self):
        bad_values = [
            ('A', 'Bakhtiyorov'),
            ('-Islom', 'Bakhtiyorov'),
            ('Islom-', 'Bakhtiyorov'),
            ("Is''lom", 'Bakhtiyorov'),
        ]
        for first_name, last_name in bad_values:
            with self.subTest(first_name=first_name):
                response = self.client.post(
                    reverse('complete_profile_name'),
                    {'first_name': first_name, 'last_name': last_name},
                    HTTP_X_REQUESTED_WITH='XMLHttpRequest',
                )
                self.assertEqual(response.status_code, 400)
                self.assertIn('first_name', response.json()['errors'])

    def test_endpoint_accepts_uzbek_russian_hyphen_and_apostrophe_names(self):
        valid_values = [
            ('O‘tkir', 'G‘ulomov'),
            ('Шердор', 'Шухратжонов'),
            ('Anna-Maria', "O'Connor"),
        ]
        for first_name, last_name in valid_values:
            with self.subTest(first_name=first_name, last_name=last_name):
                response = self.client.post(
                    reverse('complete_profile_name'),
                    {'first_name': first_name, 'last_name': last_name},
                    HTTP_X_REQUESTED_WITH='XMLHttpRequest',
                )
                self.assertEqual(response.status_code, 200)
                self.user.refresh_from_db()
                self.assertEqual(self.user.first_name, first_name)
                self.assertEqual(self.user.last_name, last_name)

    def test_endpoint_collapses_extra_spaces(self):
        response = self.client.post(
            reverse('complete_profile_name'),
            {'first_name': '  Islom   Bek  ', 'last_name': '  Bakhtiyorov  '},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, 'Islom Bek')
        self.assertEqual(self.user.last_name, 'Bakhtiyorov')

    def test_endpoint_requires_login(self):
        self.client.logout()
        response = self.client.post(
            reverse('complete_profile_name'),
            {'first_name': 'A', 'last_name': 'B'},
        )
        self.assertEqual(response.status_code, 302)

    def test_template_contains_prompt_for_missing_name(self):
        response = self.client.get(reverse('sat_menu'))
        self.assertContains(response, 'data-profile-name-gate')

    def test_template_hides_prompt_after_completion(self):
        self.user.first_name = 'Islom'
        self.user.last_name = 'Bakhtiyorov'
        self.user.save(update_fields=['first_name', 'last_name'])
        response = self.client.get(reverse('sat_menu'))
        self.assertNotContains(response, 'data-profile-name-gate')
