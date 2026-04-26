# Generated manually for AP classroom access support.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('sat', '0016_classroommembership_left_removed'),
        ('apclasses', '0006_remove_apexamevent_frq_duration_minutes_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='apexamevent',
            name='classrooms',
            field=models.ManyToManyField(
                blank=True,
                help_text='Classrooms that can access this AP mock when it is not global.',
                related_name='ap_exam_events',
                db_constraint=False,
                to='sat.classroom',
            ),
        ),
        migrations.AlterField(
            model_name='apexamevent',
            name='is_global',
            field=models.BooleanField(
                default=False,
                help_text='Make this AP mock available to all students. If off, access can be limited by classrooms or exam groups.',
            ),
        ),
    ]
