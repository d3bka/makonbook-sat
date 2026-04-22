# Generated manually to sync GlobalEventAttempt.completed_modules with the database.

from django.db import migrations, models


def sync_completed_modules_column(apps, schema_editor):
    table_name = "sat_globaleventattempt"
    column_name = "completed_modules"
    quoted_table = schema_editor.quote_name(table_name)
    quoted_column = schema_editor.quote_name(column_name)

    with schema_editor.connection.cursor() as cursor:
        existing_columns = {
            column.name
            for column in schema_editor.connection.introspection.get_table_description(
                cursor,
                table_name,
            )
        }

    if column_name not in existing_columns:
        GlobalEventAttempt = apps.get_model("sat", "GlobalEventAttempt")
        field = models.JSONField(default=list, blank=True)
        field.set_attributes_from_name(column_name)
        schema_editor.add_field(GlobalEventAttempt, field)

    schema_editor.execute(
        f"UPDATE {quoted_table} SET {quoted_column} = '[]' WHERE {quoted_column} IS NULL"
    )

    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(
            f"ALTER TABLE {quoted_table} ALTER COLUMN {quoted_column} SET DEFAULT '[]'::jsonb"
        )
        schema_editor.execute(
            f"ALTER TABLE {quoted_table} ALTER COLUMN {quoted_column} SET NOT NULL"
        )


class Migration(migrations.Migration):

    dependencies = [
        ("sat", "0014_performance_indexes"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunPython(sync_completed_modules_column, migrations.RunPython.noop),
            ],
            state_operations=[
                migrations.AddField(
                    model_name="globaleventattempt",
                    name="completed_modules",
                    field=models.JSONField(blank=True, default=list),
                ),
            ],
        ),
    ]
