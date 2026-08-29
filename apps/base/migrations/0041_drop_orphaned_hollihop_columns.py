from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ('base', '0040_generalissuereport_context_data'),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
                ALTER TABLE base_userprofile
                    DROP COLUMN IF EXISTS hollihop_client_id,
                    DROP COLUMN IF EXISTS hollihop_teacher_id,
                    DROP COLUMN IF EXISTS hollihop_employee_id,
                    DROP COLUMN IF EXISTS hollihop_status,
                    DROP COLUMN IF EXISTS hollihop_created,
                    DROP COLUMN IF EXISTS hollihop_last_synced_at;
            """,
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
