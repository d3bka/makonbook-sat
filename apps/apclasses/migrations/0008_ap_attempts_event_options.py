# Generated manually for AP classroom/mock-test logic improvements.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('apclasses', '0007_apexamevent_classrooms'),
    ]

    operations = [
        migrations.AddField(
            model_name='apexamevent',
            name='allow_guest_attempts',
            field=models.BooleanField(default=True, help_text='Allow unauthenticated guest users to start this event.'),
        ),
        migrations.AddField(
            model_name='apexamevent',
            name='max_attempts',
            field=models.PositiveIntegerField(default=1, help_text='Maximum attempts allowed per student/guest for this event.'),
        ),
        migrations.AddField(
            model_name='apexamevent',
            name='part_a_duration_minutes',
            field=models.PositiveIntegerField(blank=True, help_text='Optional event-specific override for Part A. Leave blank to use the mock exam default.', null=True),
        ),
        migrations.AddField(
            model_name='apexamevent',
            name='part_b_duration_minutes',
            field=models.PositiveIntegerField(blank=True, help_text='Optional event-specific override for Part B. Leave blank to use the mock exam default.', null=True),
        ),
        migrations.AddField(
            model_name='apexamevent',
            name='frq_duration_minutes',
            field=models.PositiveIntegerField(blank=True, help_text='Optional event-specific override for FRQ. Leave blank to use the mock exam default.', null=True),
        ),
        migrations.AddField(
            model_name='apexamattempt',
            name='attempt_number',
            field=models.PositiveIntegerField(default=1),
        ),
        migrations.AddField(
            model_name='apexamattempt',
            name='last_activity_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='apexamattempt',
            name='part_a_started_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='apexamattempt',
            name='part_b_started_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='apexamattempt',
            name='frq_started_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.RemoveConstraint(
            model_name='apexamattempt',
            name='unique_ap_attempt_per_student_event',
        ),
        migrations.AddConstraint(
            model_name='apexamattempt',
            constraint=models.UniqueConstraint(condition=models.Q(student__isnull=False), fields=('event', 'student', 'attempt_number'), name='unique_ap_attempt_number_per_student_event'),
        ),
    ]
