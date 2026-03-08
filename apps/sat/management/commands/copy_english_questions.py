# apps/sat/management/commands/copy_english_questions.py
from django.core.management.base import BaseCommand
from django.db import transaction
from apps.sat.models import Test, English_Question

class Command(BaseCommand):
    help = 'Copy English questions from DAY60 to June Predictions test'

    def add_arguments(self, parser):
        parser.add_argument(
            '--source-test',
            type=str,
            default='DAY60',
            help='Source test name (default: DAY60)'
        )
        parser.add_argument(
            '--target-test',
            type=str,
            default='June Predictions',
            help='Target test name (default: June Predictions)'
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force copy without confirmation'
        )

    @transaction.atomic
    def handle(self, *args, **options):
        source_test_name = options['source_test']
        target_test_name = options['target_test']
        force = options['force']

        try:
            # Get source test
            source_test = Test.objects.get(name=source_test_name)
            self.stdout.write(self.style.SUCCESS(f"Found source test: {source_test_name}"))
        except Test.DoesNotExist:
            self.stdout.write(self.style.ERROR(f"Source test '{source_test_name}' not found"))
            return

        # Get or create target test
        target_test, created = Test.objects.get_or_create(name=target_test_name)
        if created:
            self.stdout.write(self.style.SUCCESS(f"Created new test: {target_test_name}"))
        else:
            self.stdout.write(self.style.SUCCESS(f"Found existing test: {target_test_name}"))

        # Get English questions from source test
        source_questions_m1 = English_Question.objects.filter(test=source_test, module='module_1')
        source_questions_m2 = English_Question.objects.filter(test=source_test, module='module_2')

        total_m1 = source_questions_m1.count()
        total_m2 = source_questions_m2.count()
        total_questions = total_m1 + total_m2

        if total_questions == 0:
            self.stdout.write(self.style.WARNING(f"No English questions found in {source_test_name}"))
            return

        self.stdout.write(f"Found {total_m1} Module 1 questions and {total_m2} Module 2 questions in {source_test_name}")

        # Check if target test already has questions
        existing_questions = English_Question.objects.filter(test=target_test).count()
        if existing_questions > 0:
            self.stdout.write(self.style.WARNING(f"Target test '{target_test_name}' already has {existing_questions} English questions"))
            if not force:
                confirm = input("Continue and add more questions? (yes/no): ")
                if confirm.lower() != 'yes':
                    self.stdout.write("Operation cancelled")
                    return

        # Confirm the copy operation
        if not force:
            confirm = input(f"Copy {total_questions} English questions from '{source_test_name}' to '{target_test_name}'? (yes/no): ")
            if confirm.lower() != 'yes':
                self.stdout.write("Operation cancelled")
                return

        # Copy questions
        copied_count = 0
        
        try:
            # Copy Module 1 questions
            for question in source_questions_m1:
                new_question = English_Question(
                    test=target_test,
                    module=question.module,
                    domain=question.domain,
                    type=question.type,
                    image=question.image,
                    number=question.number,
                    passage=question.passage,
                    question=question.question,
                    a=question.a,
                    b=question.b,
                    c=question.c,
                    d=question.d,
                    graph=question.graph,
                    answer=question.answer,
                    explained=question.explained
                )
                new_question.save()
                copied_count += 1

            # Copy Module 2 questions
            for question in source_questions_m2:
                new_question = English_Question(
                    test=target_test,
                    module=question.module,
                    domain=question.domain,
                    type=question.type,
                    image=question.image,
                    number=question.number,
                    passage=question.passage,
                    question=question.question,
                    a=question.a,
                    b=question.b,
                    c=question.c,
                    d=question.d,
                    graph=question.graph,
                    answer=question.answer,
                    explained=question.explained
                )
                new_question.save()
                copied_count += 1

            self.stdout.write(self.style.SUCCESS(
                f"Successfully copied {copied_count} English questions from '{source_test_name}' to '{target_test_name}'"
            ))
            self.stdout.write(f"Source test '{source_test_name}' still contains all original questions")
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error copying questions: {str(e)}"))
            # Transaction will automatically rollback