from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("apclasses", "0002_global_secret_access"),
    ]

    operations = [
        migrations.AlterField(
            model_name="apexamattempt",
            name="student",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.CASCADE,
                related_name="ap_exam_attempts",
                to="auth.user",
            ),
        ),
        migrations.AddField(
            model_name="apexamattempt",
            name="guest_name",
            field=models.CharField(max_length=255, blank=True, default=""),
        ),
        migrations.AddField(
            model_name="apexamattempt",
            name="guest_session_key",
            field=models.CharField(max_length=64, blank=True, default="", db_index=True),
        ),
    ]
