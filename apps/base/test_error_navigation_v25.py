from django.contrib.auth.models import AnonymousUser, User
from django.test import RequestFactory, TestCase
from django.urls import reverse

from .error_views import build_error_navigation


class ErrorNavigationV25Tests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.user = User.objects.create_user(username="error_nav_v25", password="pass123")

    def _request(self, referer=""):
        request = self.factory.get("/missing-page/", HTTP_REFERER=referer)
        request.user = self.user
        return request

    def test_legacy_dashboard_is_not_used_as_go_back_target(self):
        navigation = build_error_navigation(
            self._request("http://testserver/sat/dashboard/")
        )
        self.assertEqual(navigation["error_back_url"], reverse("sat_menu"))

    def test_safe_same_site_referrer_is_preserved(self):
        navigation = build_error_navigation(
            self._request("http://testserver/sat/classroom/42/?tab=chat")
        )
        self.assertEqual(
            navigation["error_back_url"],
            "/sat/classroom/42/?tab=chat",
        )

    def test_external_referrer_is_rejected(self):
        navigation = build_error_navigation(
            self._request("https://evil.example/phishing")
        )
        self.assertEqual(navigation["error_back_url"], reverse("sat_menu"))

    def test_anonymous_fallback_goes_home(self):
        request = self.factory.get("/missing-page/")
        request.user = AnonymousUser()
        navigation = build_error_navigation(request)
        self.assertEqual(navigation["error_back_url"], "/")
