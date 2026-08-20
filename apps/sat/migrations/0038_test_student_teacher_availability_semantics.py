from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("sat", "0037_test_student_availability_semantics"),
    ]

    operations = [
        migrations.AlterField(
            model_name="test",
            name="is_available",
            field=models.BooleanField(
                "Available to students and teachers",
                db_index=True,
                default=True,
                help_text=(
                    "Controls normal authenticated Student/Teacher/Support Teacher attempts. "
                    "Guest Mode and Manager/Admin/Tester QA access remain available when this is disabled. "
                    "Existing attempts, progress and results are preserved."
                ),
            ),
        ),
    ]
