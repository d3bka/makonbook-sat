from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q

from apps.sat.models import English_Question, Test
from apps.sat.placement_offline_grading import (
    OPEN_WRITING_QUESTION_NUMBERS,
    PLACEMENT_OFFLINE_TEST_NAME,
    RULES,
    accepted_answers_text,
    rule_summary,
)


class Command(BaseCommand):
    help = (
        "Configure English writing questions 1-15 of 'Placement Test Offline' "
        "for deterministic local grading without OpenAI."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Write changes. Without this flag the command only audits the database.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        apply_changes = bool(options["apply"])
        try:
            test = Test.objects.get(name=PLACEMENT_OFFLINE_TEST_NAME)
        except Test.DoesNotExist as exc:
            raise CommandError(
                f"Test {PLACEMENT_OFFLINE_TEST_NAME!r} was not found. "
                "The name must match exactly."
            ) from exc

        # Open-response questions have no A-D options. This excludes Reading questions
        # if their numbering restarts at 1 inside the same imported test.
        blank_choices = (
            (Q(a__isnull=True) | Q(a=""))
            & (Q(b__isnull=True) | Q(b=""))
            & (Q(c__isnull=True) | Q(c=""))
            & (Q(d__isnull=True) | Q(d=""))
        )
        candidates = list(
            English_Question.objects.filter(
                test=test,
                number__in=OPEN_WRITING_QUESTION_NUMBERS,
            )
            .filter(blank_choices)
            .order_by("number", "id")
        )

        by_number: dict[int, English_Question] = {}
        duplicates: dict[int, list[int]] = {}
        for question in candidates:
            number = int(question.number)
            if number in by_number:
                duplicates.setdefault(number, [by_number[number].pk]).append(question.pk)
            else:
                by_number[number] = question

        if duplicates:
            details = ", ".join(f"Q{number}: ids={ids}" for number, ids in sorted(duplicates.items()))
            raise CommandError(f"Duplicate open-response question numbers found: {details}")

        missing = sorted(OPEN_WRITING_QUESTION_NUMBERS - set(by_number))
        if missing:
            raise CommandError(
                "Open-response questions are missing or have A-D choices: "
                + ", ".join(f"Q{number}" for number in missing)
            )

        self.stdout.write(self.style.MIGRATE_HEADING(
            f"{PLACEMENT_OFFLINE_TEST_NAME}: deterministic answer-bank audit"
        ))
        for number in sorted(by_number):
            question = by_number[number]
            rule = RULES[number]
            self.stdout.write(
                f"Q{number} (id={question.pk}): {len(rule.accepted)} reviewed variants. {rule_summary(number)}"
            )
            if apply_changes:
                question.response_type = "open_text"
                question.answer = rule.reference
                question.accepted_answers = accepted_answers_text(number)
                # The canonical validator is version-controlled Python code. Keeping the
                # DB regex field empty prevents stale admin patterns from bypassing it.
                question.answer_patterns = ""
                question.save(update_fields=[
                    "response_type",
                    "answer",
                    "accepted_answers",
                    "answer_patterns",
                    "updated_at",
                ])

        if apply_changes:
            self.stdout.write(self.style.SUCCESS(
                "Configured exactly 15 questions. No AI service is called during grading."
            ))
        else:
            self.stdout.write(self.style.WARNING(
                "Dry run only. Run the same command with --apply to save the configuration."
            ))
