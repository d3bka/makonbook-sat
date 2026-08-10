from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("ratings", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterField(
            model_name="ratingassessment",
            name="teacher",
            field=models.ForeignKey(
                on_delete=models.deletion.CASCADE,
                related_name="rating_assessments_given",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
