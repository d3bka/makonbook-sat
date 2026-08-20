from django.core.management.base import BaseCommand

from apps.sat.models import Test
from apps.sat.test_icon_service import ensure_default_test_icon, is_auto_test_icon, regenerate_auto_test_icon


class Command(BaseCommand):
    help = "Generate MakonBook branded fallback icons for tests without a custom icon."

    def add_arguments(self, parser):
        parser.add_argument(
            "--refresh-auto",
            action="store_true",
            help="Regenerate icons that were previously auto-generated (custom uploads are untouched).",
        )

    def handle(self, *args, **options):
        created = 0
        refreshed = 0
        skipped = 0
        failed = 0
        for test in Test.objects.all().order_by("name"):
            try:
                if test.icon and test.icon.name:
                    if options["refresh_auto"] and is_auto_test_icon(test.icon):
                        if regenerate_auto_test_icon(test):
                            refreshed += 1
                        else:
                            skipped += 1
                    else:
                        skipped += 1
                    continue
                if ensure_default_test_icon(test):
                    created += 1
                else:
                    skipped += 1
            except Exception as exc:
                failed += 1
                self.stderr.write(self.style.ERROR(f"{test.name}: {exc}"))

        self.stdout.write(
            self.style.SUCCESS(
                f"Default test icons complete. Created: {created}; refreshed: {refreshed}; "
                f"skipped/custom: {skipped}; failed: {failed}."
            )
        )
