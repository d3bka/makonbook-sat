from django.contrib.auth.models import Group
from django.test import TestCase

from .models import English_Question, Test
from .test_management_service import rename_test_preserving_relations


class ManagedTestServiceTests(TestCase):
    def test_rename_moves_questions_and_groups_instead_of_cloning_or_orphaning(self):
        group = Group.objects.create(name="RenameTestGroup")
        test = Test.objects.create(name="OLD TEST")
        test.groups.add(group)
        question = English_Question.objects.create(
            test=test,
            module="module_1",
            number=1,
            question="Prompt",
            a="A", b="B", c="C", d="D",
            answer="A",
        )
        renamed = rename_test_preserving_relations(test, "NEW TEST")
        question.refresh_from_db()
        self.assertFalse(Test.objects.filter(pk="OLD TEST").exists())
        self.assertEqual(question.test_id, "NEW TEST")
        self.assertTrue(renamed.groups.filter(pk=group.pk).exists())
