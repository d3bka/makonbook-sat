from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("sat", "0035_structured_test_import_pdfs"),
    ]

    operations = [
        migrations.AddField(
            model_name="test",
            name="is_available",
            field=models.BooleanField(
                db_index=True,
                default=True,
                help_text=(
                    "When disabled, nobody can start, resume, autosave, or submit this test. "
                    "Existing attempts and results are preserved and become usable again when reopened."
                ),
            ),
        ),
    ]
