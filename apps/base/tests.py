from django.test import TestCase
from django.urls import reverse

from .models import GeneralIssueReport


class GeneralIssueReportTests(TestCase):
    def test_anonymous_report_is_saved(self):
        response = self.client.post(reverse("submit_general_issue_report"), {
            "category": "content",
            "message": "Question 12 appears to have the wrong answer key.",
            "page_url": "https://example.test/sat/question/12",
            "page_title": "Question 12",
        })
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])
        self.assertEqual(GeneralIssueReport.objects.count(), 1)

    def test_short_report_is_rejected(self):
        response = self.client.post(reverse("submit_general_issue_report"), {"message": "bad"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(GeneralIssueReport.objects.count(), 0)

    def test_rate_limit(self):
        payload = {"message": "This is a sufficiently detailed report."}
        for _ in range(5):
            self.assertEqual(self.client.post(reverse("submit_general_issue_report"), payload).status_code, 200)
        self.assertEqual(self.client.post(reverse("submit_general_issue_report"), payload).status_code, 429)
