import django.core.validators
import django.db.models.deletion
import django.utils.timezone
from decimal import Decimal
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("sat", "0020_support_teacher_planning"),
    ]

    operations = [
        migrations.CreateModel(
            name="RatingConfig",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("alpha", models.DecimalField(decimal_places=3, default=Decimal("0.400"), help_text="Weight of the newest assessment in the monthly EWMA rating.", max_digits=4, validators=[django.core.validators.MinValueValidator(Decimal("0.001")), django.core.validators.MaxValueValidator(Decimal("1.000"))])),
                ("min_assessments_per_classroom", models.PositiveSmallIntegerField(default=2, help_text="A classroom stream qualifies after this many assessments in the month.")),
                ("min_qualifying_classrooms", models.PositiveSmallIntegerField(default=2, help_text="Minimum qualifying classroom streams required for the public board.")),
                ("teacher_edit_window_days", models.PositiveSmallIntegerField(default=7)),
                ("top_n", models.PositiveSmallIntegerField(default=30)),
                ("public_board_enabled", models.BooleanField(default=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"verbose_name": "Rating configuration", "verbose_name_plural": "Rating configuration"},
        ),
        migrations.CreateModel(
            name="RatingProfile",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("public_visible", models.BooleanField(default=True)),
                ("parent_access_code", models.CharField(blank=True, max_length=16, unique=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("user", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="rating_profile", to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name="RatingAssessment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("homework", models.DecimalField(decimal_places=1, max_digits=3, validators=[django.core.validators.MinValueValidator(0), django.core.validators.MaxValueValidator(10)])),
                ("progress", models.DecimalField(decimal_places=1, max_digits=3, validators=[django.core.validators.MinValueValidator(0), django.core.validators.MaxValueValidator(10)])),
                ("activity", models.DecimalField(decimal_places=1, max_digits=3, validators=[django.core.validators.MinValueValidator(0), django.core.validators.MaxValueValidator(10)])),
                ("attendance", models.DecimalField(decimal_places=1, max_digits=3, validators=[django.core.validators.MinValueValidator(0), django.core.validators.MaxValueValidator(10)])),
                ("behavior", models.DecimalField(decimal_places=1, max_digits=3, validators=[django.core.validators.MinValueValidator(0), django.core.validators.MaxValueValidator(10)])),
                ("comment", models.CharField(blank=True, max_length=500)),
                ("assessed_at", models.DateTimeField(db_index=True, default=django.utils.timezone.now)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("classroom", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="rating_assessments", to="sat.classroom")),
                ("student", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="rating_assessments_received", to=settings.AUTH_USER_MODEL)),
                ("teacher", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="rating_assessments_given", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-assessed_at", "-id"]},
        ),
        migrations.AddIndex(model_name="ratingassessment", index=models.Index(fields=["student", "assessed_at"], name="rating_student_date")),
        migrations.AddIndex(model_name="ratingassessment", index=models.Index(fields=["classroom", "assessed_at"], name="rating_class_date")),
        migrations.AddIndex(model_name="ratingassessment", index=models.Index(fields=["teacher", "assessed_at"], name="rating_teacher_date")),
    ]
