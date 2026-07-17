from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("base", "0039_generalissuereport")]
    operations = [
        migrations.AddField(
            model_name="generalissuereport",
            name="context_data",
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
