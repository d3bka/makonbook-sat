from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("sat", "0013_test_icon"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="testmodule",
            index=models.Index(fields=["user", "test", "attempt_id", "created"], name="sat_tm_u_t_att_cr"),
        ),
        migrations.AddIndex(
            model_name="testmodule",
            index=models.Index(fields=["user", "test", "section", "module", "created"], name="sat_tm_u_t_sec_mod"),
        ),
        migrations.AddIndex(
            model_name="testreview",
            index=models.Index(fields=["user", "test", "attempt_id", "created_at"], name="sat_tr_u_t_att_cr"),
        ),
        migrations.AddIndex(
            model_name="testreview",
            index=models.Index(fields=["user", "test", "created_at"], name="sat_tr_u_t_cr"),
        ),
        migrations.AddIndex(
            model_name="teststage",
            index=models.Index(fields=["user", "test", "created_at"], name="sat_ts_u_t_cr"),
        ),
        migrations.AddIndex(
            model_name="teststage",
            index=models.Index(fields=["user", "test", "attempt_id"], name="sat_ts_u_t_att"),
        ),
    ]
