from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ('sat', '0039_test_global_makonbook_availability_semantics'),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
                ALTER TABLE sat_classroom
                    DROP COLUMN IF EXISTS hollihop_edunit_id,
                    DROP COLUMN IF EXISTS hollihop_corporative,
                    DROP COLUMN IF EXISTS hollihop_managed,
                    DROP COLUMN IF EXISTS hollihop_last_synced_at;
            """,
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
