from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("sat", "0024_testmoduledraft"),
    ]

    operations = [
        migrations.CreateModel(
            name="GlobalEventModuleDraft",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("section", models.CharField(max_length=8)),
                ("module", models.CharField(max_length=8)),
                ("answers", models.JSONField(blank=True, default=list)),
                ("time_spent", models.JSONField(blank=True, default=list)),
                ("eliminated_choices", models.JSONField(blank=True, default=list)),
                ("marked_for_review", models.JSONField(blank=True, default=list)),
                ("current_question_index", models.PositiveIntegerField(default=0)),
                ("deadline_at", models.DateTimeField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("attempt", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="module_drafts", to="sat.globaleventattempt")),
            ],
        ),
        migrations.AddConstraint(
            model_name="globaleventmoduledraft",
            constraint=models.UniqueConstraint(fields=("attempt", "section", "module"), name="unique_guest_event_module_draft"),
        ),
        migrations.AddIndex(
            model_name="globaleventmoduledraft",
            index=models.Index(fields=["attempt", "section", "module"], name="guest_draft_attempt_step"),
        ),
        migrations.AddIndex(
            model_name="globaleventmoduledraft",
            index=models.Index(fields=["deadline_at"], name="guest_draft_deadline"),
        ),
    ]
