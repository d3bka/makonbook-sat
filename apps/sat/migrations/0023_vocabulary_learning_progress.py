from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):
    dependencies = [
        ('sat', '0022_deterministic_open_text'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='VocabularyQuizAttempt',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('mode', models.CharField(choices=[('word_to_meaning', 'Word to meaning'), ('meaning_to_word', 'Meaning to word'), ('mixed', 'Mixed')], default='mixed', max_length=24)),
                ('selected_units', models.JSONField(blank=True, default=list)),
                ('score', models.PositiveIntegerField(default=0)),
                ('total_questions', models.PositiveIntegerField(default=0)),
                ('percentage', models.DecimalField(decimal_places=2, default=0, max_digits=5)),
                ('duration_seconds', models.PositiveIntegerField(default=0)),
                ('started_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('completed_at', models.DateTimeField(auto_now_add=True)),
                ('classroom', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='vocabulary_quiz_attempts', to='sat.classroom')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='vocabulary_quiz_attempts', to=settings.AUTH_USER_MODEL)),
            ],
            options={'ordering': ['-completed_at']},
        ),
        migrations.CreateModel(
            name='VocabularyWordProgress',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('status', models.CharField(choices=[('new', 'New'), ('learning', 'Learning'), ('mastered', 'Mastered')], default='new', max_length=16)),
                ('times_seen', models.PositiveIntegerField(default=0)),
                ('correct_count', models.PositiveIntegerField(default=0)),
                ('incorrect_count', models.PositiveIntegerField(default=0)),
                ('consecutive_correct', models.PositiveIntegerField(default=0)),
                ('last_reviewed_at', models.DateTimeField(blank=True, null=True)),
                ('mastered_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('classroom', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='vocabulary_word_progress', to='sat.classroom')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='vocabulary_word_progress', to=settings.AUTH_USER_MODEL)),
                ('word', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='student_progress', to='sat.vocabularyword')),
            ],
            options={'ordering': ['word__unit__order', 'word__id']},
        ),
        migrations.CreateModel(
            name='VocabularyQuizAnswer',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('prompt', models.TextField()),
                ('selected_answer', models.TextField(blank=True)),
                ('correct_answer', models.TextField()),
                ('is_correct', models.BooleanField(default=False)),
                ('attempt', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='answers', to='sat.vocabularyquizattempt')),
                ('word', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='quiz_answers', to='sat.vocabularyword')),
            ],
            options={'ordering': ['id']},
        ),
        migrations.AddConstraint(
            model_name='vocabularywordprogress',
            constraint=models.UniqueConstraint(fields=('user', 'classroom', 'word'), name='unique_vocab_progress_scope'),
        ),
        migrations.AddIndex(
            model_name='vocabularywordprogress',
            index=models.Index(fields=['user', 'classroom', 'status'], name='vocab_prog_scope_status'),
        ),
        migrations.AddIndex(
            model_name='vocabularywordprogress',
            index=models.Index(fields=['classroom', 'last_reviewed_at'], name='vocab_prog_class_last'),
        ),
        migrations.AddIndex(
            model_name='vocabularyquizattempt',
            index=models.Index(fields=['user', 'classroom', 'completed_at'], name='vocab_quiz_scope_date'),
        ),
    ]
