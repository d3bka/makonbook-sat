# Generated manually for classroom multi-membership lifecycle support.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('sat', '0015_sync_completed_modules'),
    ]

    operations = [
        migrations.AlterField(
            model_name='classroommembership',
            name='status',
            field=models.CharField(
                choices=[
                    ('pending', 'Pending'),
                    ('approved', 'Approved'),
                    ('rejected', 'Rejected'),
                    ('left', 'Left'),
                    ('removed', 'Removed'),
                ],
                default='pending',
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name='classroommembership',
            name='left_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='classroommembership',
            name='removed_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
