# Generated manually for support teacher planning module.

import django.core.validators
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('sat', '0019_alter_testreview_score'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='SupportTeacherProfile',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, null=True)),
                ('updated_at', models.DateTimeField(auto_now=True, null=True)),
                ('display_name', models.CharField(blank=True, max_length=255)),
                ('telegram_username', models.CharField(blank=True, help_text='Telegram username without @.', max_length=80)),
                ('subjects', models.CharField(blank=True, help_text='Example: SAT Math, Reading, Writing', max_length=255)),
                ('bio', models.TextField(blank=True)),
                ('is_active', models.BooleanField(default=True)),
                ('sort_order', models.PositiveIntegerField(default=0)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='created_support_teacher_profiles', to=settings.AUTH_USER_MODEL)),
                ('user', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='support_teacher_profile', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Support Teacher',
                'verbose_name_plural': 'Support Teachers',
                'ordering': ['sort_order', 'display_name', 'user__first_name', 'user__username'],
            },
        ),
        migrations.CreateModel(
            name='SupportTeacherAvailability',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, null=True)),
                ('updated_at', models.DateTimeField(auto_now=True, null=True)),
                ('day_of_week', models.PositiveSmallIntegerField(choices=[(0, 'Monday'), (1, 'Tuesday'), (2, 'Wednesday'), (3, 'Thursday'), (4, 'Friday'), (5, 'Saturday'), (6, 'Sunday')])),
                ('start_time', models.TimeField()),
                ('end_time', models.TimeField()),
                ('is_active', models.BooleanField(default=True)),
                ('note', models.CharField(blank=True, max_length=255)),
                ('teacher', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='availabilities', to='sat.supportteacherprofile')),
            ],
            options={
                'verbose_name': 'Support Teacher Availability',
                'verbose_name_plural': 'Support Teacher Availabilities',
                'ordering': ['day_of_week', 'start_time', 'end_time'],
                'unique_together': {('teacher', 'day_of_week', 'start_time', 'end_time')},
            },
        ),
        migrations.CreateModel(
            name='SupportLessonBooking',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, null=True)),
                ('updated_at', models.DateTimeField(auto_now=True, null=True)),
                ('start_at', models.DateTimeField(db_index=True)),
                ('end_at', models.DateTimeField(db_index=True)),
                ('status', models.CharField(choices=[('scheduled', 'Scheduled'), ('completed', 'Completed'), ('cancelled', 'Cancelled')], db_index=True, default='scheduled', max_length=20)),
                ('student_note', models.TextField(blank=True)),
                ('cancellation_reason', models.TextField(blank=True)),
                ('marked_completed_at', models.DateTimeField(blank=True, null=True)),
                ('student', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='support_lesson_bookings', to=settings.AUTH_USER_MODEL)),
                ('teacher', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='bookings', to='sat.supportteacherprofile')),
            ],
            options={
                'verbose_name': 'Support Lesson Booking',
                'verbose_name_plural': 'Support Lesson Bookings',
                'ordering': ['-start_at'],
                'indexes': [models.Index(fields=['teacher', 'status', 'start_at'], name='sat_support_teacher_8782b5_idx'), models.Index(fields=['student', 'status', 'start_at'], name='sat_support_student_1993b3_idx')],
            },
        ),
        migrations.CreateModel(
            name='SupportTeacherReview',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, null=True)),
                ('updated_at', models.DateTimeField(auto_now=True, null=True)),
                ('rating', models.PositiveSmallIntegerField(validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(5)])),
                ('feedback', models.TextField(blank=True)),
                ('booking', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='review', to='sat.supportlessonbooking')),
                ('student', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='support_teacher_reviews', to=settings.AUTH_USER_MODEL)),
                ('teacher', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='reviews', to='sat.supportteacherprofile')),
            ],
            options={
                'verbose_name': 'Support Teacher Review',
                'verbose_name_plural': 'Support Teacher Reviews',
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddConstraint(
            model_name='supportlessonbooking',
            constraint=models.UniqueConstraint(condition=models.Q(('status', 'scheduled')), fields=('teacher', 'start_at', 'end_at'), name='unique_scheduled_support_lesson_slot'),
        ),
    ]
