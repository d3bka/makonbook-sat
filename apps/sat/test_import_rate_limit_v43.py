from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import RequestFactory, TestCase, override_settings

from .test_import_rate_limit import check_test_import_submit_limit


@override_settings(
    TEST_IMPORT_RATE_LIMIT_ENABLED=True,
    TEST_IMPORT_SUBMIT_COOLDOWN_SECONDS=30,
    TEST_IMPORT_RATE_LIMIT_MAX=10,
    TEST_IMPORT_RATE_LIMIT_WINDOW_SECONDS=600,
)
class TestImportSubmitLimitTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(username="manager-limit-test", password="x")
        self.factory = RequestFactory()

    def _request(self):
        request = self.factory.post("/sat/test-imports/new/")
        request.user = self.user
        return request

    def test_second_immediate_submission_is_blocked(self):
        first = check_test_import_submit_limit(self._request())
        second = check_test_import_submit_limit(self._request())
        self.assertTrue(first.allowed)
        self.assertFalse(second.allowed)
        self.assertEqual(second.scope, "cooldown")
