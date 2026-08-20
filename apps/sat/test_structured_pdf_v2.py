import io

import fitz
from django.test import SimpleTestCase

from .test_import_service import _parse_structured_pdf


class StructuredPdfV2Tests(SimpleTestCase):
    def _pdf(self):
        doc = fitz.open()
        page = doc.new_page(width=595, height=842)
        y = 40
        lines = [
            "[[MAKONBOOK_STRUCTURED_PDF:2]]",
            "[[SECTION:EBRW]]",
            "[[MODULE:1]]",
            "[[QUESTION:1]]",
            "[[TYPE:MCQ]]",
            "[[PASSAGE]]",
            "[[VISUAL:QUESTION]]",
        ]
        for line in lines:
            page.insert_text((45, y), line, fontsize=9)
            y += 16
        # A visual region that is not text; parser should crop it locally.
        page.draw_rect(fitz.Rect(150, y, 430, y + 65), color=(0, 0, 0), fill=(0.9, 0.9, 0.9))
        page.insert_text((170, y + 24), "TABLE VISUAL", fontsize=13)
        y += 78
        tail = [
            "[[/VISUAL:QUESTION]]",
            "Researchers compared the values in the table.",
            "[[/PASSAGE]]",
            "[[PROMPT]]",
            "Which choice is supported?",
            "[[/PROMPT]]",
            "[[A]]A text[[/A]]",
            "[[B]]B text[[/B]]",
            "[[C]]C text[[/C]]",
            "[[D]]D text[[/D]]",
            "[[ANSWER]]C[[/ANSWER]]",
            "[[EXPLANATION]][[/EXPLANATION]]",
            "[[END_QUESTION]]",
        ]
        for line in tail:
            page.insert_text((45, y), line, fontsize=9)
            y += 16
        data = doc.tobytes()
        doc.close()
        return data

    def test_v2_crops_main_visual_and_keeps_it_out_of_text(self):
        parsed, meta = _parse_structured_pdf(self._pdf(), "english")
        self.assertEqual(meta["structured_version"], 2)
        self.assertEqual(len(parsed), 1)
        module, item = parsed[0]
        self.assertEqual(module, "module_1")
        self.assertTrue(item["graph"])
        self.assertNotIn("VISUAL:QUESTION", item["passage"])
        self.assertNotIn("TABLE VISUAL", item["passage"])
        self.assertEqual(item["answer"], "C")
        self.assertTrue(item["_visual_assets"]["main"][0].startswith(b"\x89PNG"))
