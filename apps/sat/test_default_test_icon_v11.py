from django.test import SimpleTestCase
from PIL import Image
import io

from .test_icon_service import build_default_test_icon_png, extract_day_number


class DefaultTestIconTests(SimpleTestCase):
    def test_day_number_parser(self):
        self.assertEqual(extract_day_number("DAY 60"), 60)
        self.assertEqual(extract_day_number("day 7"), 7)
        self.assertEqual(extract_day_number("57"), 57)
        self.assertIsNone(extract_day_number("Placement Test"))

    def test_generated_icon_keeps_expected_dimensions(self):
        payload = build_default_test_icon_png("DAY 60")
        image = Image.open(io.BytesIO(payload))
        self.assertEqual(image.size, (500, 220))
        self.assertEqual(image.format, "PNG")

    def test_different_day_numbers_generate_different_pixels(self):
        self.assertNotEqual(build_default_test_icon_png("DAY 60"), build_default_test_icon_png("DAY 61"))
