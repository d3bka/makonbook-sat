from django.db import migrations


def repair_missing_telegram_tables(apps, schema_editor):
    """Repair databases where migration history exists but telegram tables were lost.

    This is intentionally idempotent. It addresses the production/admin error
    `relation "generated_user" does not exist` without touching existing rows.
    """
    connection = schema_editor.connection
    existing = set(connection.introspection.table_names())

    for model_name in ('TelegramAdmin', 'BulkUserRequest', 'GeneratedUser'):
        model = apps.get_model('telegram_bot', model_name)
        table = model._meta.db_table
        if table not in existing:
            schema_editor.create_model(model)
            existing = set(connection.introspection.table_names())


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ('telegram_bot', '0002_alter_generateduser_password'),
    ]

    operations = [
        migrations.RunPython(repair_missing_telegram_tables, noop_reverse),
    ]
