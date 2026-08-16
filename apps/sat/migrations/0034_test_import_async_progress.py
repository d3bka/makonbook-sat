from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("sat", "0033_test_import_pipeline"),
    ]

    operations = [
        migrations.AddField(
            model_name="testimportjob",
            name="celery_task_id",
            field=models.CharField(blank=True, db_index=True, max_length=255),
        ),
        migrations.AddField(
            model_name="testimportjob",
            name="progress_percent",
            field=models.PositiveSmallIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="testimportjob",
            name="progress_stage",
            field=models.CharField(blank=True, max_length=64),
        ),
        migrations.AddField(
            model_name="testimportjob",
            name="progress_message",
            field=models.CharField(blank=True, max_length=500),
        ),
        migrations.AddField(
            model_name="testimportjob",
            name="queued_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="testimportjob",
            name="processing_started_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="testimportjob",
            name="processing_heartbeat_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name="testimportjob",
            name="status",
            field=models.CharField(
                choices=[
                    ("uploaded", "Uploaded"),
                    ("queued", "Queued"),
                    ("processing", "Processing"),
                    ("review_required", "Review required"),
                    ("changes_requested", "Changes requested"),
                    ("ready_to_publish", "Ready to publish"),
                    ("publishing", "Publishing"),
                    ("published", "Published"),
                    ("failed", "Failed"),
                ],
                db_index=True,
                default="uploaded",
                max_length=32,
            ),
        ),
    ]
