from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import apps.sat.storages


class Migration(migrations.Migration):
    dependencies = [
        ('sat', '0032_classroom_access_defaults_v33_3'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='test',
            name='published_at',
            field=models.DateTimeField(blank=True, db_index=True, help_text='When this test became visible to students. Used for the NEW badge.', null=True),
        ),
        migrations.CreateModel(
            name='TestImportJob',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=400)),
                ('source_pdf', models.FileField(storage=apps.sat.storages.PrivateStorage(), upload_to='sat/test_imports/source/')),
                ('answer_pdf', models.FileField(blank=True, null=True, storage=apps.sat.storages.PrivateStorage(), upload_to='sat/test_imports/answers/')),
                ('requested_test_type', models.CharField(choices=[('auto', 'Auto detect'), ('full', 'Full SAT'), ('english', 'Reading & Writing'), ('math', 'Math')], default='auto', max_length=20)),
                ('detected_test_type', models.CharField(blank=True, max_length=20)),
                ('status', models.CharField(choices=[('uploaded', 'Uploaded'), ('processing', 'Processing'), ('review_required', 'Review required'), ('changes_requested', 'Changes requested'), ('ready_to_publish', 'Ready to publish'), ('publishing', 'Publishing'), ('published', 'Published'), ('failed', 'Failed')], db_index=True, default='uploaded', max_length=32)),
                ('required_approvals', models.PositiveSmallIntegerField(default=2)),
                ('ai_model', models.CharField(blank=True, max_length=80)),
                ('page_count', models.PositiveIntegerField(default=0)),
                ('structure_data', models.JSONField(blank=True, default=dict)),
                ('processing_log', models.JSONField(blank=True, default=list)),
                ('error_message', models.TextField(blank=True)),
                ('processed_at', models.DateTimeField(blank=True, null=True)),
                ('published_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('created_by', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='created_test_imports', to=settings.AUTH_USER_MODEL)),
                ('published_test', models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='import_job', to='sat.test')),
            ],
            options={'ordering': ['-created_at']},
        ),
        migrations.CreateModel(
            name='TestImportQuestion',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('section', models.CharField(choices=[('english', 'Reading & Writing'), ('math', 'Math')], max_length=16)),
                ('module', models.CharField(choices=[('module_1', 'Module 1'), ('module_2', 'Module 2')], max_length=16)),
                ('number', models.PositiveIntegerField()),
                ('passage', models.TextField(blank=True)),
                ('question', models.TextField(blank=True)),
                ('a', models.TextField(blank=True)),
                ('b', models.TextField(blank=True)),
                ('c', models.TextField(blank=True)),
                ('d', models.TextField(blank=True)),
                ('answer', models.CharField(blank=True, max_length=400)),
                ('explanation', models.TextField(blank=True)),
                ('image', models.ImageField(blank=True, null=True, storage=apps.sat.storages.PublicStorage(), upload_to='sat/test_imports/question_images/')),
                ('image_a', models.ImageField(blank=True, null=True, storage=apps.sat.storages.PublicStorage(), upload_to='sat/test_imports/choice_images/')),
                ('image_b', models.ImageField(blank=True, null=True, storage=apps.sat.storages.PublicStorage(), upload_to='sat/test_imports/choice_images/')),
                ('image_c', models.ImageField(blank=True, null=True, storage=apps.sat.storages.PublicStorage(), upload_to='sat/test_imports/choice_images/')),
                ('image_d', models.ImageField(blank=True, null=True, storage=apps.sat.storages.PublicStorage(), upload_to='sat/test_imports/choice_images/')),
                ('response_type', models.CharField(choices=[('multiple_choice', 'Multiple choice'), ('open_text', 'Open text')], default='multiple_choice', max_length=24)),
                ('written', models.BooleanField(default=False)),
                ('graph', models.BooleanField(default=False)),
                ('choice_graph', models.BooleanField(default=False)),
                ('source_page', models.PositiveIntegerField(blank=True, null=True)),
                ('ai_confidence', models.FloatField(default=0)),
                ('validation_status', models.CharField(choices=[('ok', 'OK'), ('warning', 'Warning'), ('error', 'Error')], db_index=True, default='ok', max_length=12)),
                ('validation_errors', models.JSONField(blank=True, default=list)),
                ('audit_verdict', models.CharField(blank=True, max_length=20)),
                ('audit_severity', models.CharField(blank=True, max_length=20)),
                ('audit_confidence', models.FloatField(blank=True, null=True)),
                ('audit_summary', models.TextField(blank=True)),
                ('audit_verified_answer', models.CharField(blank=True, max_length=400)),
                ('audit_recommended_fix', models.TextField(blank=True)),
                ('raw_payload', models.JSONField(blank=True, default=dict)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('job', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='questions', to='sat.testimportjob')),
            ],
            options={'ordering': ['section', 'module', 'number', 'id']},
        ),
        migrations.CreateModel(
            name='TestImportReview',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('verdict', models.CharField(choices=[('pending', 'Pending'), ('approved', 'Approved'), ('changes_requested', 'Changes requested')], db_index=True, default='pending', max_length=24)),
                ('note', models.TextField(blank=True)),
                ('reviewed_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('job', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='reviews', to='sat.testimportjob')),
                ('reviewer', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='test_import_reviews', to=settings.AUTH_USER_MODEL)),
            ],
            options={'ordering': ['created_at']},
        ),
        migrations.CreateModel(
            name='MakonNotification',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('type', models.CharField(choices=[('test_review', 'Test review'), ('test_published', 'Test published')], max_length=32)),
                ('title', models.CharField(max_length=180)),
                ('message', models.CharField(blank=True, max_length=500)),
                ('url', models.CharField(blank=True, max_length=500)),
                ('is_read', models.BooleanField(db_index=True, default=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='makon_notifications', to=settings.AUTH_USER_MODEL)),
            ],
            options={'ordering': ['-created_at']},
        ),
        migrations.AddIndex(
            model_name='testimportjob',
            index=models.Index(fields=['status', '-created_at'], name='sat_import_status_created'),
        ),
        migrations.AddIndex(
            model_name='testimportquestion',
            index=models.Index(fields=['job', 'section', 'module', 'number'], name='sat_import_q_slot'),
        ),
        migrations.AddIndex(
            model_name='testimportquestion',
            index=models.Index(fields=['job', 'validation_status'], name='sat_import_q_validation'),
        ),
        migrations.AddConstraint(
            model_name='testimportreview',
            constraint=models.UniqueConstraint(fields=('job', 'reviewer'), name='unique_import_reviewer'),
        ),
        migrations.AddIndex(
            model_name='makonnotification',
            index=models.Index(fields=['user', 'is_read', '-created_at'], name='makon_notice_user_unread'),
        ),
    ]
