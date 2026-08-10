from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.contrib.auth.hashers import make_password
from django.db import migrations, models
import django.db.models.deletion


def seed_support_topics_and_manager(apps, schema_editor):
    Group = apps.get_model('auth', 'Group')
    User = apps.get_model('auth', 'User')
    SupportLessonTitle = apps.get_model('sat', 'SupportLessonTitle')
    SupportLessonTopic = apps.get_model('sat', 'SupportLessonTopic')

    manager_group, _ = Group.objects.get_or_create(name='Manager')
    manager, created = User.objects.get_or_create(
        username='manager',
        defaults={
            'first_name': 'MakonBook',
            'last_name': 'Manager',
            'is_active': True,
            'is_staff': False,
            'is_superuser': False,
            'password': make_password(None),
        },
    )
    manager.groups.add(manager_group)

    seed = [
        (
            'Math',
            'SAT Math support topics.',
            [
                ('Algebra', 60),
                ('Advanced Math', 60),
                ('Problem-Solving & Data Analysis', 60),
                ('Geometry & Trigonometry', 60),
                ('Review Math mistakes', 60),
            ],
        ),
        (
            'Reading & Writing',
            'SAT Reading & Writing support topics.',
            [
                ('Information & Ideas', 60),
                ('Craft & Structure', 60),
                ('Expression of Ideas', 60),
                ('Standard English Conventions', 60),
                ('Review Reading & Writing mistakes', 60),
            ],
        ),
        (
            'Test Strategy',
            'Planning, timing, and full-test review.',
            [
                ('Time management', 60),
                ('Module strategy', 60),
                ('Full test review', 60),
                ('Other question', 60),
            ],
        ),
    ]

    for title_order, (title_name, description, topics) in enumerate(seed, start=1):
        title, _ = SupportLessonTitle.objects.get_or_create(
            name=title_name,
            defaults={
                'description': description,
                'sort_order': title_order,
                'is_active': True,
            },
        )
        for topic_order, (topic_name, duration) in enumerate(topics, start=1):
            SupportLessonTopic.objects.get_or_create(
                title=title,
                name=topic_name,
                defaults={
                    'default_duration_minutes': duration,
                    'default_capacity': 20,
                    'sort_order': topic_order,
                    'is_active': True,
                },
            )


def reverse_seed(apps, schema_editor):
    # Do not delete the manager account, groups, or topics on rollback. They may
    # already contain production data by the time a rollback is attempted.
    pass


class Migration(migrations.Migration):
    dependencies = [
        ('sat', '0030_student_goal_v32_qs_top_200'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='SupportLessonTitle',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, null=True)),
                ('updated_at', models.DateTimeField(auto_now=True, null=True)),
                ('name', models.CharField(max_length=120, unique=True)),
                ('description', models.CharField(blank=True, max_length=255)),
                ('sort_order', models.PositiveIntegerField(default=0)),
                ('is_active', models.BooleanField(default=True)),
            ],
            options={
                'verbose_name': 'Support Lesson Title',
                'verbose_name_plural': 'Support Lesson Titles',
                'ordering': ['sort_order', 'name'],
            },
        ),
        migrations.CreateModel(
            name='SupportLessonTopic',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, null=True)),
                ('updated_at', models.DateTimeField(auto_now=True, null=True)),
                ('name', models.CharField(max_length=160)),
                ('description', models.CharField(blank=True, max_length=255)),
                ('default_duration_minutes', models.PositiveSmallIntegerField(default=60, validators=[MinValueValidator(15), MaxValueValidator(180)])),
                ('default_capacity', models.PositiveSmallIntegerField(default=20, help_text='Default maximum number of students in one grouped support session.', validators=[MinValueValidator(1), MaxValueValidator(100)])),
                ('sort_order', models.PositiveIntegerField(default=0)),
                ('is_active', models.BooleanField(default=True)),
                ('title', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='topics', to='sat.supportlessontitle')),
            ],
            options={
                'verbose_name': 'Support Lesson Topic',
                'verbose_name_plural': 'Support Lesson Topics',
                'ordering': ['title__sort_order', 'title__name', 'sort_order', 'name'],
            },
        ),
        migrations.AddConstraint(
            model_name='supportlessontopic',
            constraint=models.UniqueConstraint(fields=('title', 'name'), name='unique_support_topic_in_title'),
        ),
        migrations.CreateModel(
            name='SupportLessonSession',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, null=True)),
                ('updated_at', models.DateTimeField(auto_now=True, null=True)),
                ('start_at', models.DateTimeField(db_index=True)),
                ('end_at', models.DateTimeField(db_index=True)),
                ('status', models.CharField(choices=[('scheduled', 'Scheduled'), ('completed', 'Completed'), ('cancelled', 'Cancelled')], db_index=True, default='scheduled', max_length=20)),
                ('meeting_link', models.URLField(blank=True)),
                ('teacher_note', models.TextField(blank=True)),
                ('max_students', models.PositiveSmallIntegerField(default=20, validators=[MinValueValidator(1), MaxValueValidator(100)])),
                ('is_open_for_requests', models.BooleanField(default=True, help_text='If enabled, later requests for this same topic may automatically join this session.')),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='created_support_lesson_sessions', to=settings.AUTH_USER_MODEL)),
                ('lesson_topic', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='sessions', to='sat.supportlessontopic')),
                ('teacher', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='sessions', to='sat.supportteacherprofile')),
            ],
            options={
                'verbose_name': 'Support Lesson Session',
                'verbose_name_plural': 'Support Lesson Sessions',
                'ordering': ['start_at'],
            },
        ),
        migrations.AddIndex(
            model_name='supportlessonsession',
            index=models.Index(fields=['teacher', 'status', 'start_at'], name='sat_sup_session_teacher_idx'),
        ),
        migrations.AddIndex(
            model_name='supportlessonsession',
            index=models.Index(fields=['lesson_topic', 'status', 'start_at'], name='sat_sup_session_topic_idx'),
        ),
        migrations.AddConstraint(
            model_name='supportlessonsession',
            constraint=models.UniqueConstraint(condition=models.Q(('status', 'scheduled')), fields=('teacher', 'start_at', 'end_at'), name='unique_support_teacher_session_slot'),
        ),
        migrations.RemoveConstraint(
            model_name='supportlessonbooking',
            name='unique_scheduled_support_lesson_slot',
        ),
        migrations.AddField(
            model_name='supportlessonbooking',
            name='lesson_title',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='bookings', to='sat.supportlessontitle'),
        ),
        migrations.AddField(
            model_name='supportlessonbooking',
            name='lesson_topic',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='bookings', to='sat.supportlessontopic'),
        ),
        migrations.AddField(
            model_name='supportlessonbooking',
            name='session',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='bookings', to='sat.supportlessonsession'),
        ),
        migrations.AlterField(
            model_name='supportlessonbooking',
            name='start_at',
            field=models.DateTimeField(blank=True, db_index=True, null=True),
        ),
        migrations.AlterField(
            model_name='supportlessonbooking',
            name='end_at',
            field=models.DateTimeField(blank=True, db_index=True, null=True),
        ),
        migrations.AlterField(
            model_name='supportlessonbooking',
            name='status',
            field=models.CharField(choices=[('requested', 'Waiting for teacher'), ('scheduled', 'Scheduled'), ('completed', 'Completed'), ('cancelled', 'Cancelled'), ('no_show', 'No-show')], db_index=True, default='requested', max_length=20),
        ),
        migrations.AlterModelOptions(
            name='supportlessonbooking',
            options={'ordering': ['-created_at'], 'verbose_name': 'Support Lesson Booking', 'verbose_name_plural': 'Support Lesson Bookings'},
        ),
        migrations.AddIndex(
            model_name='supportlessonbooking',
            index=models.Index(fields=['teacher', 'status', 'lesson_topic'], name='sat_sup_booking_topic_idx'),
        ),
        migrations.AddConstraint(
            model_name='supportlessonbooking',
            constraint=models.UniqueConstraint(condition=models.Q(('session__isnull', False)), fields=('student', 'session'), name='unique_student_per_support_session'),
        ),
        migrations.AddConstraint(
            model_name='supportlessonbooking',
            constraint=models.UniqueConstraint(condition=models.Q(('lesson_topic__isnull', False), ('status', 'requested')), fields=('student', 'teacher', 'lesson_topic'), name='unique_pending_support_topic_request'),
        ),
        migrations.AlterModelOptions(
            name='supportteacherreview',
            options={'ordering': ['-created_at'], 'verbose_name': 'Support Teacher Review (Private)', 'verbose_name_plural': 'Support Teacher Reviews (Private)'},
        ),
        migrations.RunPython(seed_support_topics_and_manager, reverse_seed),
    ]
