import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("base", "0038_passwordresetcode"),
    ]

    operations = [
        migrations.CreateModel(
            name="GeneralIssueReport",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("reporter_name", models.CharField(blank=True, max_length=160)),
                ("reporter_email", models.EmailField(blank=True, max_length=254)),
                ("category", models.CharField(choices=[("technical", "Technical problem"), ("content", "Question or content problem"), ("account", "Account or access problem"), ("rating", "Rating problem"), ("suggestion", "Suggestion"), ("other", "Other")], default="technical", max_length=30)),
                ("message", models.TextField(max_length=4000)),
                ("page_url", models.CharField(blank=True, max_length=1000)),
                ("page_title", models.CharField(blank=True, max_length=300)),
                ("user_agent", models.CharField(blank=True, max_length=1000)),
                ("status", models.CharField(choices=[("new", "New"), ("reviewing", "Reviewing"), ("resolved", "Resolved"), ("rejected", "Rejected")], db_index=True, default="new", max_length=20)),
                ("admin_note", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("reporter", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="general_issue_reports", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.AddIndex(model_name="generalissuereport", index=models.Index(fields=["status", "created_at"], name="base_issue_status_date")),
    ]
