from pathlib import Path

from django.conf import settings
from django.template.loader import render_to_string
from django.test import SimpleTestCase


class TestFlowModalRegressionTests(SimpleTestCase):
    def test_finish_summary_is_hidden_in_initial_html(self):
        html = render_to_string("test/shared/flow_overlays.html")
        self.assertIn('id="finishSummaryModal"', html)
        self.assertIn('aria-hidden="true"', html)
        self.assertRegex(html, r'id="finishSummaryModal"[^>]*\shidden(?:\s|>)')

    def test_exam_theme_hides_closed_dialogs(self):
        css = (Path(settings.BASE_DIR) / "templates/test/shared/exam_theme_v17.html").read_text(
            encoding="utf-8"
        )
        self.assertIn(".test-flow-modal {\n    display: none !important;", css)
        self.assertIn(".test-flow-modal.is-open", css)
        self.assertIn(".test-flow-modal[hidden]", css)

    def test_core_controls_hidden_property_and_all_cancel_buttons(self):
        javascript = (
            Path(settings.BASE_DIR) / "static/assets/js/sat-test-core-v13.js"
        ).read_text(encoding="utf-8")
        self.assertIn("modal.hidden = false;", javascript)
        self.assertIn("modal.hidden = true;", javascript)
        self.assertIn("querySelectorAll('[data-cancel-submit]')", javascript)
