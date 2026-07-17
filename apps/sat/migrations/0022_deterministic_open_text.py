from django.db import migrations, models


def add_or_upgrade_open_text_fields(apps, schema_editor):
    """Support both the stable v2 schema and a database that briefly ran the old AI v3 migration."""
    EnglishQuestion = apps.get_model("sat", "English_Question")
    table = EnglishQuestion._meta.db_table
    connection = schema_editor.connection

    with connection.cursor() as cursor:
        columns = {
            column.name
            for column in connection.introspection.get_table_description(cursor, table)
        }

    quoted_table = schema_editor.quote_name(table)
    column_sql = {
        "response_type": "varchar(24) NOT NULL DEFAULT 'multiple_choice'",
        "accepted_answers": "text NOT NULL DEFAULT ''",
        "answer_patterns": "text NOT NULL DEFAULT ''",
    }
    for name, sql_type in column_sql.items():
        if name in columns:
            continue
        quoted_column = schema_editor.quote_name(name)
        schema_editor.execute(
            f"ALTER TABLE {quoted_table} ADD COLUMN {quoted_column} {sql_type}"
        )
        columns.add(name)

    # Preserve useful data when upgrading a database that already ran the old
    # per-answer AI migration. Old AI-only columns/tables remain unused and can
    # be removed later with a separately reviewed cleanup migration.
    with connection.cursor() as cursor:
        if "ai_reference_answer" in columns:
            cursor.execute(
                f"UPDATE {quoted_table} "
                "SET accepted_answers = ai_reference_answer "
                "WHERE response_type = %s "
                "AND (accepted_answers IS NULL OR accepted_answers = '') "
                "AND ai_reference_answer IS NOT NULL "
                "AND ai_reference_answer <> ''",
                ["ai_sentence"],
            )
        cursor.execute(
            f"UPDATE {quoted_table} SET response_type = %s WHERE response_type = %s",
            ["open_text", "ai_sentence"],
        )


class Migration(migrations.Migration):
    dependencies = [("sat", "0020_support_teacher_planning")]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunPython(
                    add_or_upgrade_open_text_fields,
                    reverse_code=migrations.RunPython.noop,
                )
            ],
            state_operations=[
                migrations.AddField(
                    model_name="english_question",
                    name="response_type",
                    field=models.CharField(
                        choices=[
                            ("multiple_choice", "Multiple choice"),
                            ("open_text", "Open text (deterministic matching)"),
                        ],
                        default="multiple_choice",
                        max_length=24,
                    ),
                ),
                migrations.AddField(
                    model_name="english_question",
                    name="accepted_answers",
                    field=models.TextField(
                        blank=True,
                        help_text="One accepted full answer per line. Matching ignores case, repeated spaces, and final punctuation.",
                    ),
                ),
                migrations.AddField(
                    model_name="english_question",
                    name="answer_patterns",
                    field=models.TextField(
                        blank=True,
                        help_text="Optional regular expressions, one per line. Each pattern must match the entire normalized response.",
                    ),
                ),
            ],
        )
    ]
