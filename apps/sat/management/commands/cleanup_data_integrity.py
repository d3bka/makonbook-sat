import csv
import re
from collections import defaultdict
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Count

from apps.sat.models import English_Question, Math_Question, TestModule, TestReview


CYRILLIC_CHOICE_MAP = str.maketrans({
    "А": "A", "а": "A",
    "В": "B", "в": "B",
    "С": "C", "с": "C",
    "Д": "D", "д": "D",
})
VALID_CHOICES = {"A", "B", "C", "D"}
NUMERIC_RE = re.compile(r"^[-+]?\d+(?:[.,/]\d+)?$")
CHOICE_PREFIX_RE = re.compile(r"^\s*([ABCDАВСД])\s*(?:[\.)\]\-:–—]|\s)+\s*", re.IGNORECASE)


def normalize_choice_answer(value):
    if value is None:
        return ""
    cleaned = str(value).strip().translate(CYRILLIC_CHOICE_MAP).upper()
    # Sometimes imported answers are like "A." or "B)".
    cleaned = re.sub(r"[^A-Z0-9+\-./,]", "", cleaned)
    if cleaned[:1] in VALID_CHOICES and len(cleaned) <= 2:
        return cleaned[:1]
    return str(value).strip().translate(CYRILLIC_CHOICE_MAP)


def strip_choice_prefix(value):
    if value is None:
        return value
    original = str(value)
    current = original.strip()
    # Strip repeated labels: "A. A) answer" -> "answer".
    for _ in range(3):
        new = CHOICE_PREFIX_RE.sub("", current).strip()
        if new == current:
            break
        current = new
    return current


def is_numeric_like(value):
    if not value:
        return False
    value = str(value).strip().replace(" ", "")
    return bool(NUMERIC_RE.match(value))


class Command(BaseCommand):
    help = "Safely clean MakonBook auth/question data integrity issues. Dry-run by default."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="Actually write changes to the database. Default is dry-run.")
        parser.add_argument("--fix-auth", action="store_true", help="Fix duplicate emails/usernames case-insensitively.")
        parser.add_argument("--fix-questions", action="store_true", help="Fix safe question import issues: choice prefixes, Cyrillic answers, numeric math written flag.")
        parser.add_argument("--all", action="store_true", help="Run both --fix-auth and --fix-questions.")
        parser.add_argument("--export-dir", default="data_cleanup_reports", help="Directory for CSV reports.")

    def handle(self, *args, **options):
        apply = options["apply"]
        fix_auth = options["fix_auth"] or options["all"]
        fix_questions = options["fix_questions"] or options["all"]
        export_dir = Path(options["export_dir"])
        export_dir.mkdir(parents=True, exist_ok=True)

        if not fix_auth and not fix_questions:
            self.stdout.write(self.style.WARNING("Nothing selected. Use --fix-auth, --fix-questions, or --all."))
            return

        self.stdout.write(self.style.WARNING("MODE: APPLY" if apply else "MODE: DRY RUN"))

        auth_rows = []
        question_rows = []

        if fix_auth:
            auth_rows = self.cleanup_auth(apply=apply)
            self.write_csv(export_dir / "auth_cleanup_actions.csv", auth_rows, ["action", "user_id", "old_username", "new_username", "old_email", "new_email", "reason"])

        if fix_questions:
            question_rows = self.cleanup_questions(apply=apply)
            self.write_csv(export_dir / "question_cleanup_actions.csv", question_rows, ["section", "question_id", "test", "module", "number", "field", "old_value", "new_value", "reason"])

        summary = export_dir / "cleanup_summary.md"
        summary.write_text(
            "# MakonBook cleanup summary\n\n"
            f"Mode: {'APPLY' if apply else 'DRY RUN'}\n\n"
            f"Auth actions: {len(auth_rows)}\n\n"
            f"Question actions: {len(question_rows)}\n",
            encoding="utf-8",
        )
        self.stdout.write(self.style.SUCCESS(f"Done. Reports written to {export_dir}"))

    def write_csv(self, path, rows, fieldnames):
        with path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for row in rows:
                writer.writerow({k: row.get(k, "") for k in fieldnames})

    def user_score(self, user):
        score = 0
        score += TestModule.objects.filter(user=user).count() * 10
        score += TestReview.objects.filter(user=user).count() * 20
        if user.last_login:
            score += 5
        if user.is_staff or user.is_superuser:
            score += 100
        try:
            score += user.socialaccount_set.count() * 30
        except Exception:
            pass
        # Prefer older account if all else equal.
        score += max(0, 1000000 - int(user.id)) / 1000000
        return score

    def cleanup_auth(self, apply=False):
        User = get_user_model()
        rows = []

        users = list(User.objects.all().order_by("id"))

        email_groups = defaultdict(list)
        for user in users:
            email = (user.email or "").strip().lower()
            if email:
                email_groups[email].append(user)

        username_groups = defaultdict(list)
        for user in users:
            username = (user.get_username() or "").strip().lower()
            if username:
                username_groups[username].append(user)

        with transaction.atomic():
            for email, group in email_groups.items():
                if len(group) <= 1:
                    continue
                canonical = sorted(group, key=lambda u: self.user_score(u), reverse=True)[0]
                for user in group:
                    if user.pk == canonical.pk:
                        continue
                    old_email = user.email
                    new_email = f"archived-user-{user.pk}@makonbook.local"
                    rows.append({
                        "action": "archive_duplicate_email",
                        "user_id": user.pk,
                        "old_username": user.username,
                        "new_username": user.username,
                        "old_email": old_email,
                        "new_email": new_email,
                        "reason": f"duplicate email {email}; kept user_id={canonical.pk}",
                    })
                    if apply:
                        user.email = new_email
                        user.save(update_fields=["email"])

            # Refresh users after email changes.
            users = list(User.objects.all().order_by("id"))
            username_groups = defaultdict(list)
            for user in users:
                username = (user.get_username() or "").strip().lower()
                if username:
                    username_groups[username].append(user)

            for username_lower, group in username_groups.items():
                if len(group) <= 1:
                    continue
                canonical = sorted(group, key=lambda u: self.user_score(u), reverse=True)[0]
                for user in group:
                    if user.pk == canonical.pk:
                        continue
                    old_username = user.username
                    base = re.sub(r"[^a-zA-Z0-9_@.+-]", "_", old_username).strip("_") or "user"
                    new_username = f"{base}_{user.pk}"
                    while User.objects.filter(username__iexact=new_username).exclude(pk=user.pk).exists():
                        new_username = f"{base}_{user.pk}_{User.objects.count()}"
                    rows.append({
                        "action": "rename_duplicate_username",
                        "user_id": user.pk,
                        "old_username": old_username,
                        "new_username": new_username,
                        "old_email": user.email,
                        "new_email": user.email,
                        "reason": f"duplicate username case-insensitive {username_lower}; kept user_id={canonical.pk}",
                    })
                    if apply:
                        user.username = new_username
                        user.save(update_fields=["username"])

            if not apply:
                transaction.set_rollback(True)

        return rows

    def cleanup_questions(self, apply=False):
        rows = []
        with transaction.atomic():
            rows.extend(self.cleanup_question_model("english", English_Question, apply=apply))
            rows.extend(self.cleanup_question_model("math", Math_Question, apply=apply))
            if not apply:
                transaction.set_rollback(True)
        return rows

    def cleanup_question_model(self, section, Model, apply=False):
        rows = []
        qs = Model.objects.select_related("test").all().order_by("test_id", "module", "number", "id")
        for q in qs:
            changed_fields = []
            for field in ["a", "b", "c", "d"]:
                old = getattr(q, field, None)
                if old is None:
                    continue
                new = strip_choice_prefix(old)
                if new != old:
                    setattr(q, field, new)
                    changed_fields.append(field)
                    rows.append(self.qrow(section, q, field, old, new, "stripped imported choice label prefix"))

            old_answer = q.answer
            normalized = normalize_choice_answer(old_answer)
            if old_answer and normalized != old_answer:
                setattr(q, "answer", normalized)
                changed_fields.append("answer")
                rows.append(self.qrow(section, q, "answer", old_answer, normalized, "normalized answer letters/Cyrillic lookalikes"))

            if section == "math":
                answer = str(getattr(q, "answer", "") or "").strip()
                written = bool(getattr(q, "written", False))
                if answer and not written and answer.upper() not in VALID_CHOICES and is_numeric_like(answer):
                    setattr(q, "written", True)
                    changed_fields.append("written")
                    rows.append(self.qrow(section, q, "written", False, True, "numeric math answer should be written/grid-in"))

            if apply and changed_fields:
                q.save(update_fields=sorted(set(changed_fields)))
        return rows

    def qrow(self, section, q, field, old, new, reason):
        return {
            "section": section,
            "question_id": q.pk,
            "test": getattr(q.test, "name", "") if getattr(q, "test_id", None) else "",
            "module": q.module,
            "number": q.number,
            "field": field,
            "old_value": old,
            "new_value": new,
            "reason": reason,
        }
