import csv
from collections import defaultdict, Counter
from pathlib import Path

from django.core.management.base import BaseCommand

from apps.sat.models import English_Question, Math_Question


VALID_CHOICES = {"A", "B", "C", "D"}
CYRILLIC = set("АВСДавсд")


def blank(value):
    return value is None or str(value).strip() == ""


class Command(BaseCommand):
    help = "Export unsafe question issues that need manual review. Does not modify data."

    def add_arguments(self, parser):
        parser.add_argument("--export-dir", default="manual_review_reports")

    def handle(self, *args, **options):
        export_dir = Path(options["export_dir"])
        export_dir.mkdir(parents=True, exist_ok=True)
        rows = []
        rows.extend(self.scan("english", English_Question))
        rows.extend(self.scan("math", Math_Question))
        path = export_dir / "manual_question_review.csv"
        with path.open("w", newline="", encoding="utf-8") as f:
            fieldnames = ["severity", "section", "issue", "test", "module", "number", "question_id", "details"]
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for row in rows:
                writer.writerow(row)
        self.stdout.write(self.style.SUCCESS(f"Exported {len(rows)} rows to {path}"))

    def scan(self, section, Model):
        rows = []
        grouped = defaultdict(list)
        for q in Model.objects.select_related("test").all().order_by("test_id", "module", "number", "id"):
            test_name = q.test.name if q.test_id else ""
            key = (test_name, q.module, q.number)
            grouped[key].append(q)
            if not q.test_id:
                rows.append(self.row("ERROR", section, "missing_test", q, "Question is not attached to any Test."))
            if blank(q.answer):
                rows.append(self.row("ERROR", section, "blank_answer", q, "Answer is empty."))
            elif section == "english" and str(q.answer).strip().translate(str.maketrans({"А":"A","В":"B","С":"C","Д":"D","а":"A","в":"B","с":"C","д":"D"})).upper() not in VALID_CHOICES:
                rows.append(self.row("ERROR", section, "invalid_english_mcq_answer", q, f"answer={q.answer!r}"))
            elif section == "math" and not getattr(q, "written", False) and str(q.answer).strip().upper() not in VALID_CHOICES:
                rows.append(self.row("ERROR", section, "invalid_math_mcq_answer_or_missing_written_flag", q, f"answer={q.answer!r}; written={q.written}"))
            if section == "english" and blank(q.passage):
                rows.append(self.row("WARN", section, "blank_passage", q, "English question has no passage."))
            has_image = bool(getattr(q, "image", None))
            if blank(q.question) and not has_image:
                rows.append(self.row("ERROR", section, "blank_question_no_image", q, "Question text is empty and no question image is attached."))
            choices = [q.a, q.b, q.c, q.d]
            if not getattr(q, "written", False):
                normalized = [str(c or "").strip().lower() for c in choices if not blank(c)]
                dupes = [item for item, count in Counter(normalized).items() if count > 1]
                if dupes:
                    rows.append(self.row("WARN", section, "duplicate_choice_text", q, f"duplicates={dupes}"))
        for (test, module, number), items in grouped.items():
            if test and module and number is not None and len(items) > 1:
                ids = [q.pk for q in items]
                rows.append({"severity":"ERROR", "section":section, "issue":"duplicate_question_number_in_test_module", "test":test, "module":module, "number":number, "question_id":";".join(map(str, ids)), "details":f"ids={ids}"})
        return rows

    def row(self, severity, section, issue, q, details):
        return {
            "severity": severity,
            "section": section,
            "issue": issue,
            "test": q.test.name if q.test_id else "",
            "module": q.module,
            "number": q.number,
            "question_id": q.pk,
            "details": details,
        }
