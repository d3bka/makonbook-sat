from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.sat.guest_views import calculate_attempt_breakdown
from apps.sat.models import GlobalEvent, GlobalEventAttempt


class Command(BaseCommand):
    help = (
        "Recalculate submitted Guest Mode SAT scores using the current scoring engine. "
        "Useful after scoring-logic updates."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--event",
            dest="event_slug",
            help="Optional GlobalEvent slug. If omitted, all submitted Guest attempts are rescored.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show score changes without writing them to the database.",
        )

    def handle(self, *args, **options):
        event_slug = (options.get("event_slug") or "").strip()
        dry_run = bool(options.get("dry_run"))

        queryset = (
            GlobalEventAttempt.objects.filter(status="submitted")
            .select_related("event", "event__test", "guest")
            .order_by("id")
        )

        if event_slug:
            if not GlobalEvent.objects.filter(slug=event_slug).exists():
                raise CommandError(f"GlobalEvent with slug '{event_slug}' does not exist.")
            queryset = queryset.filter(event__slug=event_slug)

        total = queryset.count()
        changed = 0
        unchanged = 0

        self.stdout.write(
            f"Checking {total} submitted Guest attempt(s)"
            + (f" for event '{event_slug}'" if event_slug else "")
            + (" [DRY RUN]" if dry_run else "")
            + "..."
        )

        for attempt in queryset.iterator(chunk_size=100):
            old_score = attempt.score
            old_raw = attempt.raw_score
            old_answered = attempt.answered_questions
            breakdown = calculate_attempt_breakdown(attempt)

            new_score = breakdown["total_score"]
            new_raw = breakdown["total_raw"]
            new_answered = (
                attempt.answers.exclude(selected_answer__isnull=True)
                .exclude(selected_answer="")
                .count()
            )

            score_changed = (
                old_score is None
                or float(old_score) != float(new_score)
                or old_raw != new_raw
                or old_answered != new_answered
            )

            if not score_changed:
                unchanged += 1
                continue

            changed += 1
            self.stdout.write(
                f"  #{attempt.pk} {attempt.event.slug}: "
                f"score {old_score} -> {new_score}; raw {old_raw} -> {new_raw}"
            )

            if not dry_run:
                with transaction.atomic():
                    attempt.score = new_score
                    attempt.raw_score = new_raw
                    attempt.answered_questions = new_answered
                    attempt.save(update_fields=["score", "raw_score", "answered_questions"])

        self.stdout.write(
            self.style.SUCCESS(
                f"Done. Changed: {changed}; unchanged: {unchanged}; total: {total}."
                + (" No attempt rows were written." if dry_run else "")
            )
        )
