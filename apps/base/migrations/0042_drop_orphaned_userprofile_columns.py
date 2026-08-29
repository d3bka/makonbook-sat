from django.db import migrations


class Migration(migrations.Migration):
    """Drop columns left on base_userprofile by an abandoned "offline student
    credentials delivery" feature. They were added out-of-band (never by a
    migration) and are not present on the UserProfile model, so every INSERT
    from the create_user_profile signal omitted the NOT NULL ones and raised
    IntegrityError -- breaking account registration in production.

    Same pattern as 0041_drop_orphaned_hollihop_columns: pure database cleanup,
    no state operations, IF EXISTS so it is a no-op on a clean database.
    """

    dependencies = [
        ('base', '0041_drop_orphaned_hollihop_columns'),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
                ALTER TABLE base_userprofile
                    DROP COLUMN IF EXISTS middle_name,
                    DROP COLUMN IF EXISTS phone_number,
                    DROP COLUMN IF EXISTS must_change_password,
                    DROP COLUMN IF EXISTS credentials_delivery_status,
                    DROP COLUMN IF EXISTS credentials_last_sent_at;
            """,
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
