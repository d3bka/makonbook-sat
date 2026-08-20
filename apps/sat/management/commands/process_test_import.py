from django.core.management.base import BaseCommand, CommandError

from apps.sat.models import TestImportJob
from apps.sat.test_import_service import process_import_job


class Command(BaseCommand):
    help = "Parse and validate one staged structured-PDF import locally, without Celery/Redis."

    def add_arguments(self, parser):
        parser.add_argument("job_id", type=int)
        parser.add_argument(
            "--with-audit",
            action="store_true",
            help="Also run the optional AI answer audit after deterministic PDF parsing.",
        )

    def handle(self, *args, **options):
        try:
            job = TestImportJob.objects.get(pk=options["job_id"])
        except TestImportJob.DoesNotExist as exc:
            raise CommandError("Test import job not found.") from exc
        if job.status == TestImportJob.STATUS_PROCESSING:
            raise CommandError("This import is already processing. Do not start a second processor for the same job.")
        if job.status in {TestImportJob.STATUS_PUBLISHED, TestImportJob.STATUS_PUBLISHING}:
            raise CommandError("Published imports cannot be processed again.")
        self.stdout.write(f"Processing import #{job.pk} locally: {job.name}")
        try:
            process_import_job(job.pk, run_audit=bool(options["with_audit"]))
        except Exception as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(self.style.SUCCESS(f"Import #{job.pk} is ready for review."))
