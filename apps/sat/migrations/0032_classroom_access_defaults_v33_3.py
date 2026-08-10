from django.db import migrations, models
import django.db.models.deletion


def backfill_classroom_access_policies(apps, schema_editor):
    """Infer only unanimous legacy bulk settings.

    The old classroom-wide screens materialized the same rows on every approved
    student but did not persist the classroom intent itself. If all approved
    students agree, that is safe to carry forward as the classroom default. Mixed
    classrooms are left without an inferred policy to avoid broadening access.
    """
    Classroom = apps.get_model('sat', 'Classroom')
    ClassroomMembership = apps.get_model('sat', 'ClassroomMembership')
    StudentSectionAccess = apps.get_model('sat', 'StudentSectionAccess')
    StudentPracticeTestAccess = apps.get_model('sat', 'StudentPracticeTestAccess')
    ClassroomSectionAccessPolicy = apps.get_model('sat', 'ClassroomSectionAccessPolicy')
    ClassroomPracticeTestAccessPolicy = apps.get_model('sat', 'ClassroomPracticeTestAccessPolicy')
    Test = apps.get_model('sat', 'Test')

    section_keys = ('practice_tests', 'vocabulary', 'admissions')
    all_test_ids = set(Test.objects.values_list('pk', flat=True))

    for classroom in Classroom.objects.all().iterator():
        membership_ids = list(
            ClassroomMembership.objects.filter(
                classroom=classroom,
                role='student',
                status='approved',
            ).values_list('pk', flat=True)
        )
        if not membership_ids:
            continue

        section_values_by_membership = {}
        for membership_id in membership_ids:
            existing = dict(
                StudentSectionAccess.objects.filter(
                    membership_id=membership_id,
                    section__in=section_keys,
                ).values_list('section', 'has_access')
            )
            section_values_by_membership[membership_id] = {
                section: bool(existing.get(section, False))
                for section in section_keys
            }

        for section in section_keys:
            values = {
                section_values_by_membership[membership_id][section]
                for membership_id in membership_ids
            }
            if len(values) == 1:
                ClassroomSectionAccessPolicy.objects.update_or_create(
                    classroom_id=classroom.pk,
                    section=section,
                    defaults={'has_access': values.pop()},
                )

        eligible_ids = [
            membership_id
            for membership_id in membership_ids
            if section_values_by_membership[membership_id]['practice_tests']
        ]
        if not eligible_ids:
            continue

        access_sets = []
        for membership_id in eligible_ids:
            access_sets.append(frozenset(
                StudentPracticeTestAccess.objects.filter(
                    membership_id=membership_id,
                    has_access=True,
                ).values_list('test_id', flat=True)
            ))

        if not access_sets or len(set(access_sets)) != 1:
            continue

        selected_ids = set(access_sets[0])
        if not selected_ids:
            continue

        mode = 'all' if all_test_ids and selected_ids == all_test_ids else 'selected'
        policy, _ = ClassroomPracticeTestAccessPolicy.objects.update_or_create(
            classroom_id=classroom.pk,
            defaults={'access_mode': mode},
        )
        if mode == 'selected':
            policy.selected_tests.set(selected_ids)
        else:
            policy.selected_tests.clear()


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ('sat', '0031_support_group_sessions_manager'),
    ]

    operations = [
        migrations.CreateModel(
            name='ClassroomSectionAccessPolicy',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('section', models.CharField(choices=[('practice_tests', 'Practice Tests'), ('vocabulary', 'Vocabulary'), ('admissions', 'Admissions')], max_length=50)),
                ('has_access', models.BooleanField(default=False)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('classroom', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='section_access_policies', to='sat.classroom')),
            ],
            options={
                'verbose_name': 'Classroom Section Access Policy',
                'verbose_name_plural': 'Classroom Section Access Policies',
                'ordering': ['section'],
                'unique_together': {('classroom', 'section')},
            },
        ),
        migrations.CreateModel(
            name='ClassroomPracticeTestAccessPolicy',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('access_mode', models.CharField(choices=[('all', 'All practice tests'), ('selected', 'Selected practice tests')], default='selected', max_length=20)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('classroom', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='practice_test_access_policy', to='sat.classroom')),
                ('selected_tests', models.ManyToManyField(blank=True, related_name='classroom_access_policies', to='sat.test')),
            ],
            options={
                'verbose_name': 'Classroom Practice Test Access Policy',
                'verbose_name_plural': 'Classroom Practice Test Access Policies',
            },
        ),
        migrations.RunPython(backfill_classroom_access_policies, noop_reverse),
    ]
