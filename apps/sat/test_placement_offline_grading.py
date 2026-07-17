from __future__ import annotations

from io import StringIO

from django.core.management import call_command
from django.test import SimpleTestCase, TestCase

from .answer_matching import check_english_answer, reference_answer
from .models import English_Question, Test
from .placement_offline_grading import PLACEMENT_OFFLINE_TEST_NAME, RULES


class DummyQuestion:
    def __init__(self, number, test_name=PLACEMENT_OFFLINE_TEST_NAME, **kwargs):
        self.pk = kwargs.pop("pk", number)
        self.number = number
        self.test_id = test_name
        self.response_type = kwargs.pop("response_type", "open_text")
        self.answer = kwargs.pop("answer", "")
        self.accepted_answers = kwargs.pop("accepted_answers", "")
        self.answer_patterns = kwargs.pop("answer_patterns", "")


class PlacementOfflineMatchingTests(SimpleTestCase):
    VALID = {
        1: "The scientist performed an analysis of the data with great care.",
        2: "Graceful birds fly south every autumn.",
        3: "Every day, she walks to school.",
        4: "After the train had left, we arrived at the station.",
        5: "There is going to be a thunderstorm.",
        6: "As I was walking to the store, the rain soaked my jacket.",
        7: "The team lost the final although they practiced hard.",
        8: "She said she would complete the project the following day.",
        9: "Working out each morning is beneficial for your health.",
        10: "In order to pass her exam, she studies diligently.",
        11: "If it rains tomorrow, the roads will be slippery.",
        12: "Had he studied harder, he would not have failed the test.",
        13: "You haven't finished your homework, have you?",
        14: "Could you please tell me where the train station is?",
        15: "On Friday, the results will be announced by the committee.",
    }

    INVALID = {
        1: "The scientist analyzed the data carefully.",
        2: "Birds migrate every winter.",  # no adjective
        3: "She walks to school.",
        4: "The train left before we arrived at the station.",
        5: "It will rain.",
        6: "Walking to the store, the rain soaked my jacket.",
        7: "The team practiced hard, so they lost the final.",
        8: "She said that she will finish the project tomorrow.",
        9: "It is healthy to exercise every morning.",
        10: "She studies hard because she wants to pass the exam.",
        11: "If it will rain tomorrow, we will stay home.",
        12: "If he studied, he would not fail the test.",
        13: "Haven't you?",
        14: "Could you tell me where is the train station?",
        15: "The committee will announce the results on Friday.",
    }

    def test_all_fifteen_accept_reviewed_variants(self):
        for number, response in self.VALID.items():
            with self.subTest(number=number, response=response):
                self.assertTrue(check_english_answer(DummyQuestion(number), response))

    def test_all_fifteen_reject_wrong_target_structures(self):
        for number, response in self.INVALID.items():
            with self.subTest(number=number, response=response):
                self.assertFalse(check_english_answer(DummyQuestion(number), response))

    def test_markup_and_contractions_are_normalized(self):
        self.assertTrue(check_english_answer(DummyQuestion(2), "__Migratory birds__ migrate every autumn."))
        self.assertTrue(check_english_answer(DummyQuestion(5), "It's going to rain!"))
        self.assertTrue(check_english_answer(DummyQuestion(12), "If he had studied, he wouldn't have failed the test."))
        self.assertTrue(check_english_answer(DummyQuestion(6), "While walking to the store, I got my jacket soaked by the rain."))

    def test_rules_are_isolated_to_exact_test_name(self):
        other = DummyQuestion(5, test_name="Placement Test", accepted_answers="It will rain.")
        self.assertTrue(check_english_answer(other, "It will rain."))
        self.assertFalse(check_english_answer(other, "It is going to rain."))

    def test_reference_answer_comes_from_version_control(self):
        question = DummyQuestion(3, answer="stale database value")
        self.assertEqual(reference_answer(question), RULES[3].reference)


class ConfigurePlacementOfflineAnswersCommandTests(TestCase):
    def setUp(self):
        self.test = Test.objects.create(name=PLACEMENT_OFFLINE_TEST_NAME)
        self.other_test = Test.objects.create(name="Another Placement Test")
        self.open_questions = []
        for number in range(1, 16):
            self.open_questions.append(English_Question.objects.create(
                test=self.test,
                module="module_1",
                number=number,
                question=f"Open question {number}",
                answer="legacy",
                a="",
                b="",
                c="",
                d="",
            ))
        # Same number but with choices: should be treated as a Reading/MCQ item and left alone.
        self.reading_question = English_Question.objects.create(
            test=self.test,
            module="module_2",
            number=1,
            question="Reading question",
            a="One",
            b="Two",
            c="Three",
            d="Four",
            answer="B",
        )
        self.other_question = English_Question.objects.create(
            test=self.other_test,
            module="module_1",
            number=1,
            question="Other test question",
            answer="legacy",
            a="",
            b="",
            c="",
            d="",
        )

    def test_dry_run_changes_nothing(self):
        call_command("configure_placement_offline_answers", stdout=StringIO())
        self.open_questions[0].refresh_from_db()
        self.assertEqual(self.open_questions[0].response_type, "multiple_choice")
        self.assertEqual(self.open_questions[0].answer, "legacy")

    def test_apply_configures_only_the_exact_open_questions(self):
        output = StringIO()
        call_command("configure_placement_offline_answers", "--apply", stdout=output)

        for number, question in enumerate(self.open_questions, start=1):
            question.refresh_from_db()
            self.assertEqual(question.response_type, "open_text")
            self.assertEqual(question.answer, RULES[number].reference)
            self.assertIn(RULES[number].accepted[0], question.accepted_answers)
            self.assertEqual(question.answer_patterns, "")

        self.reading_question.refresh_from_db()
        self.other_question.refresh_from_db()
        self.assertEqual(self.reading_question.response_type, "multiple_choice")
        self.assertEqual(self.reading_question.answer, "B")
        self.assertEqual(self.other_question.response_type, "multiple_choice")
        self.assertIn("No AI service is called", output.getvalue())
