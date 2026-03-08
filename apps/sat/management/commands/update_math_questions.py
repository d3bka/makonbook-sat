from django.core.management.base import BaseCommand
from django.db import transaction
from apps.sat.models import Test, Math_Question


class Command(BaseCommand):
    help = 'Delete math questions from DAY50 and reassign DAY59 math questions to DAY50'

    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force the operation without confirmation',
        )

    @transaction.atomic
    def handle(self, *args, **options):
        force = options['force']
        
        # Get test objects
        day50_test = Test.objects.filter(name='DAY50').first()
        day59_test = Test.objects.filter(name='DAY59').first()
        
        if not day50_test:
            self.stdout.write(self.style.ERROR("Error: Test 'DAY50' not found in database."))
            return
            
        if not day59_test:
            self.stdout.write(self.style.ERROR("Error: Test 'DAY59' not found in database."))
            return
        
        # First, count how many questions will be affected
        day50_count = Math_Question.objects.filter(test=day50_test).count()
        day59_count = Math_Question.objects.filter(test=day59_test).count()
        
        self.stdout.write(f"Found {day50_count} math questions in DAY50 (to be deleted)")
        self.stdout.write(f"Found {day59_count} math questions in DAY59 (to be reassigned to DAY50)")
        
        # Confirm action if not forced
        if not force:
            confirm = input(f"This will DELETE {day50_count} questions and MOVE {day59_count} questions. Type 'YES' to confirm: ")
            if confirm != "YES":
                self.stdout.write(self.style.WARNING("Operation cancelled."))
                return
        
        # Execute operations within a transaction
        try:
            # 1. Delete all math questions from DAY50
            result = Math_Question.objects.filter(test=day50_test).delete()
            deleted_count = result[0]
            self.stdout.write(self.style.SUCCESS(f"Successfully deleted {deleted_count} math questions from DAY50"))
            
            # 2. Update all math questions from DAY59 to point to DAY50
            updated_count = Math_Question.objects.filter(test=day59_test).update(test=day50_test)
            self.stdout.write(self.style.SUCCESS(f"Successfully updated {updated_count} math questions from DAY59 to point to DAY50"))
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error occurred: {str(e)}"))
            # The transaction will be automatically rolled back 