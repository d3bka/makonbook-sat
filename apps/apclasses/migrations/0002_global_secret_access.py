# Generated manually for AP Classes global/secret-code access
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("apclasses", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="apexamevent",
            name="is_global",
            field=models.BooleanField(
                default=False,
                help_text="Make this AP mock available to all students. If off, access can be limited by the exam groups.",
            ),
        ),
        migrations.AlterField(
            model_name="apexamevent",
            name="access_code",
            field=models.CharField(
                "Secret code",
                blank=True,
                help_text="Optional. If filled, students must enter this code before starting the AP mock exam.",
                max_length=50,
            ),
        ),
        migrations.AlterField(
            model_name="apexamevent",
            name="is_public",
            field=models.BooleanField(default=True, help_text="Show this event in the AP Classes page."),
        ),
    ]
