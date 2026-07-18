import re

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import PasswordResetCode


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    DEFAULT_FROM_EMAIL="MakonBook Support <support@makonbook.uz>",
    EMAIL_HOST_USER="support@makonbook.uz",
)
class PasswordResetEmailV27Tests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="islom6",
            first_name="Islom",
            email="islom@example.com",
            password="StrongPass123!",
            is_active=True,
        )

    def test_reset_email_has_branded_html_and_plain_text_fallback(self):
        response = self.client.post(
            reverse("forgot_password"),
            {"email": self.user.email},
        )

        self.assertRedirects(response, reverse("password_reset_confirm"))
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(PasswordResetCode.objects.count(), 1)

        message = mail.outbox[0]
        self.assertEqual(message.subject, "Reset your MakonBook password")
        self.assertEqual(message.to, [self.user.email])
        self.assertEqual(message.reply_to, ["support@makonbook.uz"])
        self.assertIn("Hi Islom", message.body)
        self.assertIn("expires in 10 minutes", message.body)
        self.assertIn(reverse("password_reset_confirm"), message.body)

        code_match = re.search(r"verification code is:\s*(\d{6})", message.body)
        self.assertIsNotNone(code_match)
        code = code_match.group(1)

        self.assertEqual(len(message.alternatives), 1)
        html_body, mimetype = message.alternatives[0]
        self.assertEqual(mimetype, "text/html")
        self.assertIn("MakonBook", html_body)
        self.assertIn("Reset your password", html_body)
        self.assertIn(code, html_body)
        self.assertIn("Continue password reset", html_body)
        self.assertIn("Keep this code private", html_body)
        self.assertIn("support@makonbook.uz", html_body)

    def test_unknown_email_keeps_generic_response_and_sends_nothing(self):
        response = self.client.post(
            reverse("forgot_password"),
            {"email": "missing@example.com"},
        )

        self.assertRedirects(response, reverse("password_reset_confirm"))
        self.assertEqual(len(mail.outbox), 0)
        self.assertEqual(PasswordResetCode.objects.count(), 0)
