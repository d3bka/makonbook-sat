from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("sat", "0025_globaleventmoduledraft"),
    ]

    operations = [
        migrations.CreateModel(
            name="MakeupTestModuleDraft",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, null=True)),
                ("updated_at", models.DateTimeField(auto_now=True, null=True)),
                ("attempt_id", models.UUIDField(editable=False)),
                ("section", models.CharField(max_length=8)),
                ("module", models.CharField(max_length=8)),
                ("answers", models.JSONField(blank=True, default=list)),
                ("time_spent", models.JSONField(blank=True, default=list)),
                ("eliminated_choices", models.JSONField(blank=True, default=list)),
                ("marked_for_review", models.JSONField(blank=True, default=list)),
                ("current_question_index", models.PositiveIntegerField(default=0)),
                ("deadline_at", models.DateTimeField()),
                ("makeup_test", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="module_drafts", to="sat.makeuptest")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="makeup_module_drafts", to="auth.user")),
            ],
        ),
        migrations.AddConstraint(
            model_name="makeuptestmoduledraft",
            constraint=models.UniqueConstraint(fields=("user", "makeup_test", "attempt_id", "section", "module"), name="sat_unique_makeup_module_draft"),
        ),
        migrations.AddIndex(
            model_name="makeuptestmoduledraft",
            index=models.Index(fields=["user", "makeup_test", "attempt_id"], name="sat_mtd_u_t_att"),
        ),
        migrations.AddIndex(
            model_name="makeuptestmoduledraft",
            index=models.Index(fields=["deadline_at"], name="sat_mtd_deadline"),
        ),
    ]
