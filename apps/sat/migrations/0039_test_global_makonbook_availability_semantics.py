from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("sat", "0038_test_student_teacher_availability_semantics"),
    ]

    operations = [
        migrations.AlterField(
            model_name="test",
            name="is_available",
            field=models.BooleanField(
                "Open for MakonBook users",
                db_index=True,
                default=True,
                help_text=(
                    "Controls all normal MakonBook test attempts for Students, Teachers and Support Teachers, "
                    "including every Classroom attempt. Guest Mode and Manager/Admin/Tester QA access remain "
                    "available when disabled. Existing attempts, progress and results are preserved."
                ),
            ),
        ),
    ]
