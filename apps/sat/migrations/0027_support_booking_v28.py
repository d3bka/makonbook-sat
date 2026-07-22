from django.db import migrations, models
import django.core.validators


def preserve_existing_availability_lengths(apps, schema_editor):
    Availability = apps.get_model('sat', 'SupportTeacherAvailability')
    for row in Availability.objects.all().only('id', 'start_time', 'end_time'):
        if not row.start_time or not row.end_time:
            continue
        start_minutes = row.start_time.hour * 60 + row.start_time.minute
        end_minutes = row.end_time.hour * 60 + row.end_time.minute
        duration = end_minutes - start_minutes
        if duration <= 0:
            continue
        # Existing records represented one exact recurring lesson. Preserve that
        # behavior; newly created records default to 60-minute generated slots.
        duration = max(15, min(duration, 180))
        Availability.objects.filter(pk=row.pk).update(slot_duration_minutes=duration)


class Migration(migrations.Migration):

    dependencies = [
        ('sat', '0026_makeuptestmoduledraft'),
    ]

    operations = [
        migrations.AddField(
            model_name='supportteacherprofile',
            name='booking_instructions',
            field=models.CharField(blank=True, help_text='Short instruction shown before a student confirms a booking.', max_length=255),
        ),
        migrations.AddField(
            model_name='supportteacherprofile',
            name='cancellation_notice_hours',
            field=models.PositiveSmallIntegerField(default=2, help_text='Students cannot cancel inside this notice window.', validators=[django.core.validators.MinValueValidator(0), django.core.validators.MaxValueValidator(168)]),
        ),
        migrations.AddField(
            model_name='supportteacherprofile',
            name='meeting_link',
            field=models.URLField(blank=True, help_text='Default Google Meet, Zoom, or other lesson link shown for scheduled lessons.'),
        ),
        migrations.AddField(
            model_name='supportteacherprofile',
            name='min_booking_notice_hours',
            field=models.PositiveSmallIntegerField(default=2, help_text='Minimum notice required before a lesson can be booked.', validators=[django.core.validators.MinValueValidator(0), django.core.validators.MaxValueValidator(168)]),
        ),
        migrations.AddField(
            model_name='supportteacheravailability',
            name='buffer_minutes',
            field=models.PositiveSmallIntegerField(default=0, help_text='Optional break between generated lesson slots.', validators=[django.core.validators.MinValueValidator(0), django.core.validators.MaxValueValidator(60)]),
        ),
        migrations.AddField(
            model_name='supportteacheravailability',
            name='slot_duration_minutes',
            field=models.PositiveSmallIntegerField(default=60, help_text='Length of each bookable lesson generated inside this weekly window.', validators=[django.core.validators.MinValueValidator(15), django.core.validators.MaxValueValidator(180)]),
        ),
        migrations.RunPython(preserve_existing_availability_lengths, migrations.RunPython.noop),
        migrations.AddField(
            model_name='supportlessonbooking',
            name='cancelled_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='supportlessonbooking',
            name='cancelled_by',
            field=models.CharField(blank=True, choices=[('student', 'Student'), ('teacher', 'Support teacher'), ('admin', 'Administrator')], max_length=20),
        ),
        migrations.AddField(
            model_name='supportlessonbooking',
            name='meeting_link',
            field=models.URLField(blank=True),
        ),
        migrations.AddField(
            model_name='supportlessonbooking',
            name='teacher_note',
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name='supportlessonbooking',
            name='topic',
            field=models.CharField(choices=[('general', 'General SAT support'), ('math', 'SAT Math'), ('reading_writing', 'Reading & Writing'), ('test_strategy', 'Test strategy'), ('review', 'Review mistakes'), ('other', 'Other')], default='general', max_length=32),
        ),
        migrations.AlterField(
            model_name='supportlessonbooking',
            name='status',
            field=models.CharField(choices=[('scheduled', 'Scheduled'), ('completed', 'Completed'), ('cancelled', 'Cancelled'), ('no_show', 'No-show')], db_index=True, default='scheduled', max_length=20),
        ),
    ]
