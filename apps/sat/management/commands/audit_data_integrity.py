from __future__ import annotations

import csv
import json
import re
import uuid
from collections import defaultdict
from pathlib import Path

from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.hashers import identify_hasher, is_password_usable
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Count
from django.utils import timezone

from apps.base.models import UserProfile
from apps.sat.models import English_Question, Math_Question, TestModule, TestReview


CHOICE_PREFIX_RE = re.compile(r"^\s*([A-Da-d])\s*(?:[\.)\-:])?\s+(.*)$", re.S)
MULTI_CHOICE_PREFIX_RE = re.compile(r"^\s*([A-Da-d])\s+\1\b", re.S)
PLACEHOLDER_RE = re.compile(r"^\s*(passage|question|text|none|null|n/a|-)\s*$", re.I)


def norm_text(value):
    return re.sub(r"\s+", " ", (value or "").strip())


def short(value, n=140):
    value = norm_text(value)
    return value[:n] + ("…" if len(value) > n else "")


def has_choice_prefix(value, letter):
    value = value or ""
    return bool(re.match(rf"^\s*{letter}\s*(?:[\.)\-:]|\s+)", value, re.I))


def choice_prefix_issue(value, letter):
    if not value:
        return False
    return has_choice_prefix(value, letter) or bool(MULTI_CHOICE_PREFIX_RE.match(value))


class Command(BaseCommand):
    help = "Audit MakonBook auth/user persistence and SAT question data integrity."

    def add_arguments(self, parser):
        parser.add_argument("--export-dir", default="data_audit_reports")
        parser.add_argument("--smoke-auth", action="store_true", help="Create/delete a temporary user to verify register/login hashing.")

    def handle(self, *args, **options):
        export_dir = Path(options["export_dir"])
        export_dir.mkdir(parents=True, exist_ok=True)

        auth_issues = []
        question_issues = []
        summary = []

        self.audit_auth(auth_issues, summary, smoke_auth=options["smoke_auth"])
        self.audit_questions(question_issues, summary)
        self.audit_saved_attempts(question_issues, summary)

        auth_csv = export_dir / "auth_issues.csv"
        question_csv = export_dir / "question_issues.csv"
        summary_md = export_dir / "summary.md"

        self.write_csv(auth_csv, auth_issues, ["severity", "issue", "user_id", "username", "email", "details"])
        self.write_csv(question_csv, question_issues, ["severity", "section", "issue", "test", "module", "number", "question_id", "details"])
        summary_md.write_text("\n".join(summary) + "\n", encoding="utf-8")

        self.stdout.write(self.style.SUCCESS(f"Auth issues: {len(auth_issues)} -> {auth_csv}"))
        self.stdout.write(self.style.SUCCESS(f"Question issues: {len(question_issues)} -> {question_csv}"))
        self.stdout.write(self.style.SUCCESS(f"Summary -> {summary_md}"))

    def write_csv(self, path, rows, fields):
        with path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            for row in rows:
                writer.writerow({field: row.get(field, "") for field in fields})

    def add_auth(self, rows, severity, issue, user=None, details=""):
        rows.append({
            "severity": severity,
            "issue": issue,
            "user_id": getattr(user, "id", "") if user else "",
            "username": getattr(user, "username", "") if user else "",
            "email": getattr(user, "email", "") if user else "",
            "details": details,
        })

    def add_question(self, rows, severity, section, issue, obj=None, details=""):
        rows.append({
            "severity": severity,
            "section": section,
            "issue": issue,
            "test": getattr(obj, "test_id", "") if obj else "",
            "module": getattr(obj, "module", "") if obj else "",
            "number": getattr(obj, "number", "") if obj else "",
            "question_id": getattr(obj, "id", "") if obj else "",
            "details": details,
        })

    def audit_auth(self, rows, summary, smoke_auth=False):
        User = get_user_model()
        users = list(User.objects.all().order_by("id"))
        summary.append(f"# MakonBook Data Integrity Audit")
        summary.append(f"Generated at: {timezone.now().isoformat()}")
        summary.append("")
        summary.append(f"## Auth/User")
        summary.append(f"Users: {len(users)}")

        for user in users:
            if not (user.username or "").strip():
                self.add_auth(rows, "ERROR", "blank_username", user)
            if not (user.email or "").strip():
                self.add_auth(rows, "WARN", "blank_email", user)
            if not is_password_usable(user.password):
                self.add_auth(rows, "INFO", "unusable_password_google_only_or_no_password", user)
            else:
                try:
                    identify_hasher(user.password)
                except Exception as exc:
                    self.add_auth(rows, "ERROR", "invalid_or_plain_password_hash", user, str(exc))
            if not UserProfile.objects.filter(user=user).exists():
                self.add_auth(rows, "ERROR", "missing_user_profile", user)

        for item in User.objects.exclude(email="").values("email").annotate(c=Count("id")):
            pass

        email_groups = defaultdict(list)
        username_groups = defaultdict(list)
        for user in users:
            if user.email:
                email_groups[user.email.strip().lower()].append(user)
            if user.username:
                username_groups[user.username.strip().lower()].append(user)
        for email, group in email_groups.items():
            if len(group) > 1:
                self.add_auth(rows, "ERROR", "duplicate_email_case_insensitive", None, f"{email}: {[u.id for u in group]}")
        for username, group in username_groups.items():
            if len(group) > 1:
                self.add_auth(rows, "ERROR", "duplicate_username_case_insensitive", None, f"{username}: {[u.id for u in group]}")

        if smoke_auth:
            self.smoke_auth(rows)

    def smoke_auth(self, rows):
        User = get_user_model()
        marker = uuid.uuid4().hex[:10]
        username = f"audit_tmp_{marker}"
        email = f"audit_tmp_{marker}@example.com"
        password = f"AuditTmp!{marker}123"
        try:
            with transaction.atomic():
                user = User.objects.create_user(username=username, email=email, password=password, is_active=True)
                authed = authenticate(username=username, password=password)
                if not authed or authed.id != user.id:
                    self.add_auth(rows, "ERROR", "smoke_auth_failed", user, "Temporary user could not authenticate after create_user().")
                raise RuntimeError("rollback temporary audit user")
        except RuntimeError as exc:
            if str(exc) != "rollback temporary audit user":
                raise

    def audit_questions(self, rows, summary):
        summary.append("")
        summary.append("## SAT Questions")
        for model, section in [(English_Question, "english"), (Math_Question, "math")]:
            qs = list(model.objects.select_related("test").all().order_by("test_id", "module", "number", "id"))
            summary.append(f"{section}: {len(qs)} questions")

            dup_keys = defaultdict(list)
            qtext_groups = defaultdict(list)
            passage_hash_groups = defaultdict(list)

            for q in qs:
                dup_keys[(q.test_id, q.module, q.number)].append(q)
                qnorm = norm_text(q.question).lower()
                if qnorm:
                    qtext_groups[qnorm].append(q)
                pnorm = norm_text(q.passage).lower()
                if pnorm:
                    passage_hash_groups[(q.test_id, q.module, hash(pnorm))].append(q)

                if not q.test_id:
                    self.add_question(rows, "ERROR", section, "missing_test", q)
                if not q.module:
                    self.add_question(rows, "ERROR", section, "missing_module", q)
                if q.number is None:
                    self.add_question(rows, "ERROR", section, "missing_number", q)
                if not norm_text(q.question):
                    self.add_question(rows, "ERROR", section, "blank_question", q)
                elif PLACEHOLDER_RE.match(norm_text(q.question)):
                    self.add_question(rows, "ERROR", section, "placeholder_question", q, short(q.question))

                if section == "english":
                    if not norm_text(q.passage):
                        self.add_question(rows, "WARN", section, "blank_passage", q)
                    elif PLACEHOLDER_RE.match(norm_text(q.passage)):
                        self.add_question(rows, "ERROR", section, "placeholder_passage", q, short(q.passage))

                is_written = bool(getattr(q, "written", False))
                answer = norm_text(q.answer).upper()
                if not answer:
                    self.add_question(rows, "ERROR", section, "blank_answer", q)
                elif section == "english" or not is_written:
                    if answer not in {"A", "B", "C", "D"}:
                        self.add_question(rows, "ERROR", section, "invalid_mcq_answer", q, f"answer={q.answer!r}")

                if section == "english" or not is_written:
                    for letter, field in [("A", "a"), ("B", "b"), ("C", "c"), ("D", "d")]:
                        value = getattr(q, field, None)
                        if not norm_text(value):
                            self.add_question(rows, "ERROR", section, f"blank_choice_{letter}", q)
                        elif choice_prefix_issue(value, letter):
                            self.add_question(rows, "WARN", section, f"choice_{letter}_contains_label_prefix", q, short(value))

                    choices = [norm_text(getattr(q, f, "")).lower() for f in ["a", "b", "c", "d"]]
                    nonblank = [c for c in choices if c]
                    if len(set(nonblank)) < len(nonblank):
                        self.add_question(rows, "WARN", section, "duplicate_choice_text", q, f"choices={nonblank}")

            for key, group in dup_keys.items():
                if len(group) > 1:
                    for q in group:
                        self.add_question(rows, "ERROR", section, "duplicate_question_number_in_test_module", q, f"ids={[x.id for x in group]}")

            for qnorm, group in qtext_groups.items():
                if len(group) > 1:
                    passage_set = {norm_text(g.passage).lower() for g in group}
                    test_set = {g.test_id for g in group}
                    if len(passage_set) > 1:
                        for q in group:
                            self.add_question(rows, "WARN", section, "same_question_text_different_passage", q, f"other_ids={[g.id for g in group if g.id != q.id]}; question={short(q.question)}")
                    elif len(test_set) > 1:
                        for q in group:
                            self.add_question(rows, "INFO", section, "same_question_reused_across_tests", q, f"other_ids={[g.id for g in group if g.id != q.id]}")

            # English reading sets: same passage should usually be contiguous inside one module.
            if section == "english":
                for (_test, _module, _hash), group in passage_hash_groups.items():
                    nums = sorted([g.number for g in group if g.number is not None])
                    if len(nums) >= 2 and nums != list(range(nums[0], nums[-1] + 1)):
                        for q in group:
                            self.add_question(rows, "WARN", section, "same_passage_non_contiguous_question_numbers", q, f"numbers={nums}; ids={[g.id for g in group]}")

    def audit_saved_attempts(self, rows, summary):
        summary.append("")
        summary.append("## Attempts/Results")
        summary.append(f"TestModule rows: {TestModule.objects.count()}")
        summary.append(f"TestReview rows: {TestReview.objects.count()}")

        for module in TestModule.objects.select_related("test", "user").all().order_by("-created")[:5000]:
            try:
                payload = json.loads(module.answers or "{}")
            except Exception as exc:
                rows.append({
                    "severity": "ERROR", "section": module.section, "issue": "invalid_answers_json",
                    "test": module.test_id, "module": module.module, "number": "", "question_id": "",
                    "details": f"TestModule id={module.id}: {exc}",
                })
                continue
            answers = payload.get("answers")
            if answers is None:
                rows.append({"severity": "WARN", "section": module.section, "issue": "answers_payload_missing_answers_key", "test": module.test_id, "module": module.module, "number": "", "question_id": "", "details": f"TestModule id={module.id}"})
            elif not isinstance(answers, list):
                rows.append({"severity": "ERROR", "section": module.section, "issue": "answers_payload_answers_not_list", "test": module.test_id, "module": module.module, "number": "", "question_id": "", "details": f"TestModule id={module.id}"})
