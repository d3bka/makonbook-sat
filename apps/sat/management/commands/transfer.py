from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group
from apps.sat.models import Test

class Command(BaseCommand):
    help = "Create group '40TESTS' and assign tests DAY1 to DAY40 to it, then show group and test ids."

    def handle(self, *args, **kwargs):
        group, created = Group.objects.get_or_create(name='40TESTS')
        if created:
            self.stdout.write(self.style.SUCCESS(f"Group '40TESTS' created with id {group.id}"))
        else:
            self.stdout.write(self.style.WARNING(f"Group '40TESTS' already exists with id {group.id}"))

        test_ids = []
        for i in range(1, 41):
            test_name = f"DAY{i}"
            test = Test.objects.filter(name=test_name).first()
            if test:
                test.groups.add(group)
                test_ids.append(test.name)
            else:
                self.stdout.write(self.style.WARNING(f"Test '{test_name}' not found."))

        self.stdout.write(self.style.SUCCESS(f"Assigned tests to group '40TESTS' (id: {group.id})"))
        self.stdout.write(f"Test names assigned: {', '.join(test_ids)}")