from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('sat', '0027_support_booking_v28'),
    ]

    operations = [
        migrations.AddField(
            model_name='supportteacherprofile',
            name='education',
            field=models.CharField(blank=True, help_text='University, degree, certification, or other public credential.', max_length=255),
        ),
        migrations.AddField(
            model_name='supportteacherprofile',
            name='headline',
            field=models.CharField(blank=True, help_text='Short public headline, for example: SAT Math specialist.', max_length=180),
        ),
        migrations.AddField(
            model_name='supportteacherprofile',
            name='languages',
            field=models.CharField(blank=True, help_text='Languages used during support lessons.', max_length=180),
        ),
        migrations.AddField(
            model_name='supportteacherprofile',
            name='sat_math_score',
            field=models.PositiveSmallIntegerField(blank=True, null=True, validators=[MinValueValidator(200), MaxValueValidator(800)]),
        ),
        migrations.AddField(
            model_name='supportteacherprofile',
            name='sat_reading_writing_score',
            field=models.PositiveSmallIntegerField(blank=True, null=True, validators=[MinValueValidator(200), MaxValueValidator(800)]),
        ),
        migrations.AddField(
            model_name='supportteacherprofile',
            name='sat_total_score',
            field=models.PositiveSmallIntegerField(blank=True, null=True, validators=[MinValueValidator(400), MaxValueValidator(1600)]),
        ),
        migrations.AddField(
            model_name='supportteacherprofile',
            name='scores_verified',
            field=models.BooleanField(default=False, help_text='Admin verification flag for publicly displayed SAT scores.'),
        ),
        migrations.AddField(
            model_name='supportteacherprofile',
            name='years_experience',
            field=models.PositiveSmallIntegerField(default=0, validators=[MinValueValidator(0), MaxValueValidator(50)]),
        ),
    ]
