from django.db import migrations, models

import apps.sat.storages


class Migration(migrations.Migration):
    dependencies = [
        ("sat", "0034_test_import_async_progress"),
    ]

    operations = [
        migrations.AlterField(
            model_name="testimportjob",
            name="source_pdf",
            field=models.FileField(
                blank=True,
                null=True,
                storage=apps.sat.storages.PrivateStorage(),
                upload_to="sat/test_imports/source/",
            ),
        ),
        migrations.AddField(
            model_name="testimportjob",
            name="english_pdf",
            field=models.FileField(
                blank=True,
                null=True,
                storage=apps.sat.storages.PrivateStorage(),
                upload_to="sat/test_imports/structured/english/",
            ),
        ),
        migrations.AddField(
            model_name="testimportjob",
            name="math_pdf",
            field=models.FileField(
                blank=True,
                null=True,
                storage=apps.sat.storages.PrivateStorage(),
                upload_to="sat/test_imports/structured/math/",
            ),
        ),
    ]
