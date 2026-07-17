from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.sat.question_audit import (
    audit_question_payloads,
    collect_questions,
    generate_audit_pdf,
    mock_audit_run,
)


class Command(BaseCommand):
    help = "Audit question-bank content with AI and generate a teacher PDF. This command never edits questions."

    def add_arguments(self, parser):
        parser.add_argument("--test", dest="test_name", help="Exact test name. Omit to audit all tests.")
        parser.add_argument("--section", choices=["all", "english", "math"], default="all")
        parser.add_argument("--model")
        parser.add_argument("--batch-size", type=int)
        parser.add_argument("--output", default="question_audit.pdf")
        parser.add_argument("--include-ok", action="store_true")
        parser.add_argument("--mock", action="store_true", help="Generate an offline sample PDF without calling OpenAI.")

    def handle(self, *args, **options):
        output = Path(options["output"]).expanduser().resolve()
        if options["mock"]:
            run = mock_audit_run()
        else:
            payload = collect_questions(test_name=options.get("test_name"), section=options["section"])
            if not payload:
                raise CommandError("No matching questions were found.")
            self.stdout.write(f"Auditing {len(payload)} questions. No database records will be modified.")
            run = audit_question_payloads(payload, model=options.get("model"), batch_size=options.get("batch_size"))
        generate_audit_pdf(run, output, include_ok=options["include_ok"])
        self.stdout.write(self.style.SUCCESS(f"PDF created: {output}"))
