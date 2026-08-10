from django.test import TestCase

from apps.sat.guest_views import (
    get_event_question_totals,
    get_event_scoring_label,
    get_event_scoring_type,
    regular_score_from_counts,
)
from apps.sat.models import English_Question, Math_Question, Test


class GuestScoringV335Tests(TestCase):
    def make_questions(self, model, test, module, count):
        model.objects.bulk_create([
            model(test=test, module=module, number=index + 1, answer="A")
            for index in range(count)
        ])

    def test_single_module_full_test_uses_400_1600_estimated_scale(self):
        test = Test.objects.create(name="Guest single-module full")
        self.make_questions(English_Question, test, "module_1", 60)
        self.make_questions(Math_Question, test, "module_1", 38)

        totals = get_event_question_totals(test)
        self.assertEqual(get_event_scoring_type(test), "sat_estimated")
        self.assertEqual(get_event_scoring_label(test), "SAT-style normalized estimate 400–1600")

        perfect = regular_score_from_counts(
            "full",
            {
                "english": {"m1": 60, "m2": 0},
                "math": {"m1": 38, "m2": 0},
            },
            totals,
        )
        zero = regular_score_from_counts(
            "full",
            {
                "english": {"m1": 0, "m2": 0},
                "math": {"m1": 0, "m2": 0},
            },
            totals,
        )
        self.assertEqual(perfect["sections"]["english"]["score"], 800)
        self.assertEqual(perfect["sections"]["math"]["score"], 800)
        self.assertEqual(perfect["total"], 1600)
        self.assertEqual(zero["total"], 400)

    def test_single_section_guest_test_uses_200_800_scale(self):
        test = Test.objects.create(name="Guest English only")
        self.make_questions(English_Question, test, "module_1", 60)
        totals = get_event_question_totals(test)

        result = regular_score_from_counts(
            "ebrw_only",
            {
                "english": {"m1": 60, "m2": 0},
                "math": {"m1": 0, "m2": 0},
            },
            totals,
        )
        self.assertEqual(get_event_scoring_type(test), "sat_estimated")
        self.assertEqual(get_event_scoring_label(test), "SAT-style normalized estimate 200–800")
        self.assertEqual(result["total"], 800)

    def test_standard_two_module_test_keeps_standard_scoring(self):
        test = Test.objects.create(name="Guest standard full")
        self.make_questions(English_Question, test, "module_1", 27)
        self.make_questions(English_Question, test, "module_2", 27)
        self.make_questions(Math_Question, test, "module_1", 22)
        self.make_questions(Math_Question, test, "module_2", 22)

        totals = get_event_question_totals(test)
        self.assertEqual(get_event_scoring_type(test), "sat_standard")
        perfect = regular_score_from_counts(
            "full",
            {
                "english": {"m1": 27, "m2": 27},
                "math": {"m1": 22, "m2": 22},
            },
            totals,
        )
        self.assertEqual(perfect["total"], 1600)
