# Generated manually for AP Classes MVP
import uuid
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models
import apps.sat.storages


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        migrations.CreateModel(
            name="APClass",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=255, unique=True)),
                ("code", models.CharField(blank=True, help_text="Example: AP-CALC-AB", max_length=50)),
                ("description", models.TextField(blank=True)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("groups", models.ManyToManyField(blank=True, related_name="ap_classes", to="auth.group")),
            ],
            options={"verbose_name": "AP Class", "verbose_name_plural": "AP Classes", "ordering": ["name"]},
        ),
        migrations.CreateModel(
            name="APMockExam",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=255)),
                ("slug", models.SlugField(blank=True, unique=True)),
                ("description", models.TextField(blank=True)),
                ("rules", models.TextField(blank=True)),
                ("status", models.CharField(choices=[("draft", "Draft"), ("published", "Published"), ("archived", "Archived")], default="draft", max_length=20)),
                ("part_a_duration_minutes", models.PositiveIntegerField(default=60, help_text="30 MCQ, no Desmos/calculator")),
                ("part_b_duration_minutes", models.PositiveIntegerField(default=45, help_text="15 MCQ, Desmos/calculator allowed")),
                ("frq_duration_minutes", models.PositiveIntegerField(default=45, help_text="FRQ pages shown on screen; students answer on paper")),
                ("show_score_immediately", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("ap_class", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="mock_exams", to="apclasses.apclass")),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
                ("groups", models.ManyToManyField(blank=True, related_name="ap_mock_exams", to="auth.group")),
            ],
            options={"verbose_name": "AP Mock Exam", "verbose_name_plural": "AP Mock Exams", "ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="APExamEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=255)),
                ("slug", models.SlugField(blank=True, unique=True)),
                ("description", models.TextField(blank=True)),
                ("rules", models.TextField(blank=True)),
                ("access_code", models.CharField(blank=True, max_length=50)),
                ("is_public", models.BooleanField(default=True)),
                ("status", models.CharField(choices=[("draft", "Draft"), ("scheduled", "Scheduled"), ("live", "Live"), ("closed", "Closed")], default="draft", max_length=20)),
                ("start_at", models.DateTimeField(blank=True, null=True)),
                ("end_at", models.DateTimeField(blank=True, null=True)),
                ("always_live", models.BooleanField(default=False, help_text="If checked, event is available 24/7 while status is Live")),
                ("allow_resume", models.BooleanField(default=True)),
                ("show_score_immediately", models.BooleanField(default=True)),
                ("show_leaderboard", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("exam", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="events", to="apclasses.apmockexam")),
            ],
            options={"verbose_name": "AP Exam Event", "verbose_name_plural": "AP Exam Events", "ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="APMultipleChoiceQuestion",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("part", models.CharField(choices=[("part_a", "Part A - 30 MCQ, no Desmos"), ("part_b", "Part B - 15 MCQ, Desmos allowed")], default="part_a", max_length=20)),
                ("number", models.PositiveIntegerField(help_text="Question number inside this AP part")),
                ("image", models.ImageField(blank=True, null=True, storage=apps.sat.storages.PublicStorage(), upload_to="apclasses/question_images", verbose_name="Question image")),
                ("passage", models.TextField(blank=True, verbose_name="Passage")),
                ("question", models.TextField(blank=True, verbose_name="Question")),
                ("a", models.TextField(blank=True, verbose_name="Choice A")),
                ("b", models.TextField(blank=True, verbose_name="Choice B")),
                ("c", models.TextField(blank=True, verbose_name="Choice C")),
                ("d", models.TextField(blank=True, verbose_name="Choice D")),
                ("e", models.TextField(blank=True, verbose_name="Choice E")),
                ("image_a", models.ImageField(blank=True, null=True, storage=apps.sat.storages.PublicStorage(), upload_to="apclasses/choice_images", verbose_name="Image A")),
                ("image_b", models.ImageField(blank=True, null=True, storage=apps.sat.storages.PublicStorage(), upload_to="apclasses/choice_images", verbose_name="Image B")),
                ("image_c", models.ImageField(blank=True, null=True, storage=apps.sat.storages.PublicStorage(), upload_to="apclasses/choice_images", verbose_name="Image C")),
                ("image_d", models.ImageField(blank=True, null=True, storage=apps.sat.storages.PublicStorage(), upload_to="apclasses/choice_images", verbose_name="Image D")),
                ("image_e", models.ImageField(blank=True, null=True, storage=apps.sat.storages.PublicStorage(), upload_to="apclasses/choice_images", verbose_name="Image E")),
                ("correct_answer", models.CharField(blank=True, choices=[("A", "A"), ("B", "B"), ("C", "C"), ("D", "D"), ("E", "E")], max_length=1)),
                ("explanation", models.TextField(blank=True)),
                ("calculator_allowed", models.BooleanField(default=False, editable=False)),
                ("desmos_allowed", models.BooleanField(default=False, editable=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("exam", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="questions", to="apclasses.apmockexam")),
            ],
            options={"verbose_name": "AP MCQ Question", "verbose_name_plural": "AP MCQ Questions", "ordering": ["exam", "part", "number"]},
        ),
        migrations.CreateModel(
            name="APFRQPage",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("page_number", models.PositiveIntegerField()),
                ("title", models.CharField(blank=True, max_length=255)),
                ("instructions", models.TextField(blank=True)),
                ("image", models.ImageField(blank=True, null=True, storage=apps.sat.storages.PublicStorage(), upload_to="apclasses/frq_pages", verbose_name="FRQ page image")),
                ("file", models.FileField(blank=True, null=True, storage=apps.sat.storages.PublicStorage(), upload_to="apclasses/frq_files", verbose_name="FRQ PDF/file")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("exam", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="frq_pages", to="apclasses.apmockexam")),
            ],
            options={"verbose_name": "AP FRQ Page", "verbose_name_plural": "AP FRQ Pages", "ordering": ["exam", "page_number"]},
        ),
        migrations.CreateModel(
            name="APExamAttempt",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("token", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("started_at", models.DateTimeField(auto_now_add=True)),
                ("submitted_at", models.DateTimeField(blank=True, null=True)),
                ("status", models.CharField(choices=[("in_progress", "In Progress"), ("submitted", "Submitted"), ("expired", "Expired")], default="in_progress", max_length=20)),
                ("score", models.DecimalField(blank=True, decimal_places=2, max_digits=8, null=True)),
                ("raw_score", models.IntegerField(default=0)),
                ("total_questions", models.PositiveIntegerField(default=0)),
                ("answered_questions", models.PositiveIntegerField(default=0)),
                ("event", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="attempts", to="apclasses.apexamevent")),
                ("student", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="ap_exam_attempts", to=settings.AUTH_USER_MODEL)),
            ],
            options={"verbose_name": "AP Exam Attempt", "verbose_name_plural": "AP Exam Attempts"},
        ),
        migrations.CreateModel(
            name="APExamAnswer",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("selected_answer", models.CharField(blank=True, max_length=1)),
                ("is_correct", models.BooleanField(default=False)),
                ("answered_at", models.DateTimeField(auto_now=True)),
                ("attempt", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="answers", to="apclasses.apexamattempt")),
                ("question", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="answers", to="apclasses.apmultiplechoicequestion")),
            ],
            options={"verbose_name": "AP Exam Answer", "verbose_name_plural": "AP Exam Answers"},
        ),
        migrations.CreateModel(
            name="APFRQSubmission",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("page_number", models.PositiveIntegerField(default=1)),
                ("image", models.ImageField(blank=True, null=True, storage=apps.sat.storages.PublicStorage(), upload_to="apclasses/frq_submissions", verbose_name="Handwritten answer image")),
                ("file", models.FileField(blank=True, null=True, storage=apps.sat.storages.PublicStorage(), upload_to="apclasses/frq_submissions", verbose_name="Handwritten answer file")),
                ("teacher_comment", models.TextField(blank=True)),
                ("score", models.DecimalField(blank=True, decimal_places=2, max_digits=6, null=True)),
                ("uploaded_at", models.DateTimeField(auto_now_add=True)),
                ("attempt", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="frq_submissions", to="apclasses.apexamattempt")),
            ],
            options={"verbose_name": "AP FRQ Submission", "verbose_name_plural": "AP FRQ Submissions", "ordering": ["attempt", "page_number"]},
        ),
        migrations.AddConstraint("APMultipleChoiceQuestion", models.UniqueConstraint(fields=("exam", "part", "number"), name="unique_ap_question_number_per_part")),
        migrations.AddConstraint("APFRQPage", models.UniqueConstraint(fields=("exam", "page_number"), name="unique_ap_frq_page_per_exam")),
        migrations.AddConstraint("APExamAttempt", models.UniqueConstraint(fields=("event", "student"), name="unique_ap_attempt_per_student_event")),
        migrations.AddConstraint("APExamAnswer", models.UniqueConstraint(fields=("attempt", "question"), name="unique_ap_answer_per_question")),
    ]
