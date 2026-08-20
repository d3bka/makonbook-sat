from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("sat", "0036_test_is_available"),
    ]

    operations = [
        migrations.AlterField(
            model_name="test",
            name="is_available",
            field=models.BooleanField(
                "Available to authenticated students",
                db_index=True,
                default=True,
                help_text=(
                    "Controls normal authenticated student/classroom attempts only. "
                    "Guest Mode and staff-side QA access remain available when this is disabled. "
                    "Existing student attempts and results are preserved."
                ),
            ),
        ),
    ]
