# sat/management/commands/swap_english_questions.py
from django.core.management.base import BaseCommand
from apps.sat.models import Test, English_Question

class Command(BaseCommand):
    help = 'Swaps all English questions between two Test instances using a dummy test as a temporary holder.'

    def add_arguments(self, parser):
        parser.add_argument('test1_name', type=str, help='Name of the first Test (e.g., DAY40)')
        parser.add_argument('test2_name', type=str, help='Name of the second Test (e.g., DAY57)')
        parser.add_argument('--dummy-test', type=str, default='dummytest', help='Name of the dummy test to use as a temporary holder (default: dummytest)')

    def handle(self, *args, **options):
        test1_name = options['test1_name']
        test2_name = options['test2_name']
        dummy_test_name = options['dummy_test']

        try:
            # Retrieve the two Test instances and the dummy test
            test1 = Test.objects.get(name=test1_name)
            test2 = Test.objects.get(name=test2_name)
            dummy_test = Test.objects.get(name=dummy_test_name)
        except Test.DoesNotExist as e:
            self.stdout.write(self.style.ERROR(f"Test not found: {e}"))
            return

        # Get all English questions for each test, grouped by module
        test1_questions_m1 = English_Question.objects.filter(test=test1, module='module_1')
        test1_questions_m2 = English_Question.objects.filter(test=test1, module='module_2')
        test2_questions_m1 = English_Question.objects.filter(test=test2, module='module_1')
        test2_questions_m2 = English_Question.objects.filter(test=test2, module='module_2')

        # Count questions for logging
        total_test1_m1 = test1_questions_m1.count()
        total_test1_m2 = test1_questions_m2.count()
        total_test2_m1 = test2_questions_m1.count()
        total_test2_m2 = test2_questions_m2.count()

        if total_test1_m1 != total_test2_m1 or total_test1_m2 != total_test2_m2:
            self.stdout.write(self.style.WARNING(
                f"Warning: Unequal question counts - "
                f"{test1_name} (m1: {total_test1_m1}, m2: {total_test1_m2}), "
                f"{test2_name} (m1: {total_test2_m1}, m2: {total_test2_m2}). Proceeding with swap."
            ))

        # Step 1: Move test1 (e.g., DAY40) questions to dummy_test
        if total_test1_m1 > 0:
            test1_questions_m1.update(test=dummy_test)
        if total_test1_m2 > 0:
            test1_questions_m2.update(test=dummy_test)

        # Step 2: Move test2 (e.g., DAY57) questions to test1 (e.g., DAY40)
        if total_test2_m1 > 0:
            test2_questions_m1.update(test=test1)
        if total_test2_m2 > 0:
            test2_questions_m2.update(test=test1)

        # Step 3: Move dummy_test questions (originally from test1) to test2 (e.g., DAY57)
        dummy_questions_m1 = English_Question.objects.filter(test=dummy_test, module='module_1')
        dummy_questions_m2 = English_Question.objects.filter(test=dummy_test, module='module_2')
        if dummy_questions_m1.exists():
            dummy_questions_m1.update(test=test2)
        if dummy_questions_m2.exists():
            dummy_questions_m2.update(test=test2)

        self.stdout.write(self.style.SUCCESS(
            f"Successfully swapped English questions between {test1_name} and {test2_name}. "
            f"Updated: m1 ({total_test1_m1 + total_test2_m1}), m2 ({total_test1_m2 + total_test2_m2}) questions."
        ))