# Generated manually to separate SAT attempts/reviews per classroom.

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('sat', '0017_classroom_classroom_type'),
    ]

    operations = [
        migrations.AddField(
            model_name='testmodule',
            name='classroom',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='test_modules', to='sat.classroom'),
        ),
        migrations.AddField(
            model_name='testreview',
            name='classroom',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='test_reviews', to='sat.classroom'),
        ),
        migrations.AddField(
            model_name='teststage',
            name='classroom',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='test_stages', to='sat.classroom'),
        ),
    ]
