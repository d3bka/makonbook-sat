from django.test import SimpleTestCase

from .test_import_service import _clean_structured_text


class StructuredPdfTextProfileTests(SimpleTestCase):
    def test_pdf_line_wrapping_collapses_to_spaces(self):
        value = (
            "The Gleaners, painted in the realist style by Jean-François Millet, depicts peasants picking stray wheat from a field after the harvest.\n"
            "The realists’ emphasis on accurately portraying the experiences of average working people was largely a rejection of the romantic\n"
            "style evident in many paintings by Horace Vernet."
        )
        result = _clean_structured_text(value, section="english", field_name="passage")
        self.assertNotIn("\n", result)
        self.assertIn("romantic style evident", result)

    def test_explicit_break_markers_are_preserved(self):
        value = "Text 1[[BR]]First text.[[PAR]]Text 2[[BR]]Second text."
        result = _clean_structured_text(value, section="english", field_name="passage")
        self.assertEqual(result, "Text 1\nFirst text.\n\nText 2\nSecond text.")

    def test_legacy_blank_becomes_structured_blank(self):
        value = "which instead ______ blank their subjects’ positive traits"
        result = _clean_structured_text(value, section="english", field_name="passage")
        self.assertEqual(result, "which instead [[BLANK]] their subjects’ positive traits")

    def test_simple_math_choice_is_upgraded_to_katex(self):
        result = _clean_structured_text("(v² −45)(v² −10)", section="math", field_name="a")
        self.assertEqual(result, r"\((v^{2} -45)(v^{2} -10)\)")

    def test_system_prefix_is_separated_from_question_prose(self):
        value = "y = −15x + 19 y = −20x + 24 What is the solution (x, y) to the given system of equations?"
        result = _clean_structured_text(value, section="math", field_name="question")
        self.assertIn(r"\(y = -15x + 19 \quad y = -20x + 24\)", result)
        self.assertIn("\nWhat is the solution", result)

    def test_standalone_equation_line_is_preserved(self):
        value = "b − 38 = x/y\nThe given equation relates the positive numbers b, x, and y."
        result = _clean_structured_text(value, section="math", field_name="question")
        self.assertTrue(result.startswith(r"\(b - 38 = \frac{x}{y}\)\n"))

    def test_root_fraction_is_upgraded_without_changing_prose(self):
        value = "The expression (⁷√(p⁵))/√(p^(t+3)), where t is a constant, is equivalent to ⁷√(p²) for all positive values of p."
        result = _clean_structured_text(value, section="math", field_name="question")
        self.assertIn(r"\(\frac{\sqrt[7]{p^{5}}}{\sqrt{p^{t+3}}}\)", result)
        self.assertIn(r"\(\sqrt[7]{p^{2}}\)", result)

