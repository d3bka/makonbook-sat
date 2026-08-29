from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ('sat', '0040_drop_orphaned_hollihop_columns'),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
                ALTER TABLE sat_classroommembership
                    DROP COLUMN IF EXISTS hollihop_managed,
                    DROP COLUMN IF EXISTS hollihop_status,
                    DROP COLUMN IF EXISTS hollihop_last_synced_at;
            """,
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
