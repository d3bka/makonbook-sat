from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

@override_settings(
    REGISTRATION_RATE_LIMIT_ENABLED=True,
    REGISTRATION_RATE_LIMIT_IP_MAX=2,
    REGISTRATION_RATE_LIMIT_IP_WINDOW_SECONDS=600,
    REGISTRATION_RATE_LIMIT_IDENTIFIER_MAX=10,
    REGISTRATION_RATE_LIMIT_IDENTIFIER_WINDOW_SECONDS=1800,
)
class RegistrationRateLimitTests(TestCase):
    def setUp(self):
        cache.clear()

    def _post(self, suffix):
        return self.client.post(
            reverse("register"),
            {
                "username": f"rateuser{suffix}",
                "email": f"rate{suffix}@example.com",
                "password": "short",
                "confirm_password": "short",
            },
            REMOTE_ADDR="203.0.113.10",
        )

    def test_registration_posts_are_rate_limited_server_side(self):
        self.assertEqual(self._post(1).status_code, 200)
        self.assertEqual(self._post(2).status_code, 200)

        blocked = self._post(3)
        self.assertEqual(blocked.status_code, 429)
        self.assertIn("Retry-After", blocked.headers)
