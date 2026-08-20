from __future__ import annotations

from dataclasses import dataclass

from django.db import transaction
from django.db.models import Count, IntegerField, OuterRef, Subquery, Value
from django.db.models.functions import Coalesce

from .models import (
    English_Question,
    GlobalEvent,
    GlobalEventAttempt,
    Math_Question,
    StudentPracticeTestAccess,
    Test,
    TestImportJob,
    TestModuleDraft,
)
from .test_icon_service import ensure_default_test_icon, is_auto_test_icon, regenerate_auto_test_icon


@dataclass(frozen=True)
class TestDeleteImpact:
    english_questions: int
    math_questions: int
    global_events: int
    guest_attempts: int
    student_access_rows: int
    module_drafts: int

    @property
    def total_questions(self):
        return self.english_questions + self.math_questions


def _related_count_subquery(queryset, group_field: str):
    return (
        queryset
        .values(group_field)
        .annotate(total=Count("pk"))
        .values("total")[:1]
    )


def get_test_delete_impact(test: Test) -> TestDeleteImpact:
    """Return delete impact with one DB round-trip.

    The old implementation issued six independent COUNT queries. That was
    especially noticeable against MakonBook's remote PostgreSQL during every
    delete confirmation. Correlated subqueries keep the same result in one SQL
    statement without multiplying rows through several reverse joins.
    """
    zero = Value(0, output_field=IntegerField())
    row = (
        Test.objects
        .filter(pk=test.pk)
        .annotate(
            impact_english=Coalesce(
                Subquery(
                    _related_count_subquery(
                        English_Question.objects.filter(test_id=OuterRef("pk")),
                        "test_id",
                    ),
                    output_field=IntegerField(),
                ),
                zero,
            ),
            impact_math=Coalesce(
                Subquery(
                    _related_count_subquery(
                        Math_Question.objects.filter(test_id=OuterRef("pk")),
                        "test_id",
                    ),
                    output_field=IntegerField(),
                ),
                zero,
            ),
            impact_events=Coalesce(
                Subquery(
                    _related_count_subquery(
                        GlobalEvent.objects.filter(test_id=OuterRef("pk")),
                        "test_id",
                    ),
                    output_field=IntegerField(),
                ),
                zero,
            ),
            impact_guest_attempts=Coalesce(
                Subquery(
                    _related_count_subquery(
                        GlobalEventAttempt.objects.filter(event__test_id=OuterRef("pk")),
                        "event__test_id",
                    ),
                    output_field=IntegerField(),
                ),
                zero,
            ),
            impact_student_access=Coalesce(
                Subquery(
                    _related_count_subquery(
                        StudentPracticeTestAccess.objects.filter(test_id=OuterRef("pk")),
                        "test_id",
                    ),
                    output_field=IntegerField(),
                ),
                zero,
            ),
            impact_module_drafts=Coalesce(
                Subquery(
                    _related_count_subquery(
                        TestModuleDraft.objects.filter(test_id=OuterRef("pk")),
                        "test_id",
                    ),
                    output_field=IntegerField(),
                ),
                zero,
            ),
        )
        .values(
            "impact_english",
            "impact_math",
            "impact_events",
            "impact_guest_attempts",
            "impact_student_access",
            "impact_module_drafts",
        )
        .get()
    )
    return TestDeleteImpact(
        english_questions=row["impact_english"],
        math_questions=row["impact_math"],
        global_events=row["impact_events"],
        guest_attempts=row["impact_guest_attempts"],
        student_access_rows=row["impact_student_access"],
        module_drafts=row["impact_module_drafts"],
    )


def rename_test_preserving_relations(test: Test, new_name: str) -> Test:
    """Rename Test even though its legacy primary key is the name itself.

    Assigning a new value to a Django primary key and calling save() would
    insert a second Test row. Instead we create the replacement row inside one
    transaction, repoint every reverse FK/one-to-one relation, copy groups, and
    only then remove the old row.
    """
    new_name = (new_name or "").strip()
    if not new_name:
        raise ValueError("Test name cannot be empty.")
    if new_name == test.pk:
        return test
    if Test.objects.filter(name__iexact=new_name).exclude(pk=test.pk).exists():
        raise ValueError(f"A test named '{new_name}' already exists.")

    with transaction.atomic():
        old = Test.objects.select_for_update().get(pk=test.pk)
        old_groups = list(old.groups.all())
        old_icon_was_auto = is_auto_test_icon(old.icon)
        replacement = Test.objects.create(
            name=new_name,
            published_at=old.published_at,
            is_available=old.is_available,
            icon=old.icon,
        )
        replacement.groups.set(old_groups)

        # Preserve the old created timestamp even though Test.created is a
        # legacy auto_now field.
        Test.objects.filter(pk=replacement.pk).update(created=old.created)

        for relation in Test._meta.related_objects:
            if relation.many_to_many or relation.related_model._meta.auto_created:
                # Test.groups is copied above. Skip implicit through-table
                # reverse relations or we could create duplicate M2M rows.
                continue
            field = relation.field
            related_model = relation.related_model
            related_model._default_manager.filter(**{field.name: old}).update(**{field.name: replacement})

        # Removing the old row now cannot cascade the repointed relations.
        old.delete()
        replacement = Test.objects.get(pk=replacement.pk)
        if old_icon_was_auto:
            regenerate_auto_test_icon(replacement)
        return replacement


def update_test_settings(
    test: Test, *, name: str, groups, is_available: bool, icon=None, remove_icon=False
) -> Test:
    with transaction.atomic():
        current = Test.objects.select_for_update().get(pk=test.pk)
        if (name or "").strip() != current.pk:
            current = rename_test_preserving_relations(current, name)
            current = Test.objects.select_for_update().get(pk=current.pk)

        if remove_icon:
            current.icon = None
            current.is_available = bool(is_available)
            current.save(update_fields=["icon", "is_available"])
            ensure_default_test_icon(current)
        elif icon:
            current.icon = icon
            current.is_available = bool(is_available)
            current.save(update_fields=["icon", "is_available"])
        else:
            current.is_available = bool(is_available)
            current.save(update_fields=["is_available"])
            if not current.icon:
                ensure_default_test_icon(current)

        current.groups.set(groups)
        return current


def set_test_availability(test: Test, *, is_available: bool) -> Test:
    """Open/close a published test with one atomic UPDATE statement.

    A row lock + SELECT was unnecessary for a single boolean flag and made the
    Manager action wait longer on remote PostgreSQL. QuerySet.update() is
    already atomic at the statement level and does not touch attempts/history.
    """
    value = bool(is_available)
    updated = Test.objects.filter(pk=test.pk).update(is_available=value)
    if not updated:
        raise Test.DoesNotExist(f"Test '{test.pk}' no longer exists.")
    test.is_available = value
    return test


def delete_published_test(test: Test, *, allow_linked_events=False):
    """Delete the published test while preserving staging and normal history.

    English_Question/Math_Question use SET_NULL for historical reasons, so we
    delete those explicitly to avoid orphan question rows. TestReview/TestStage
    and similar historical records keep their rows and become test=NULL via
    their model policy. Linked GlobalEvent rows are CASCADE and therefore need
    explicit operator acknowledgement.
    """
    with transaction.atomic():
        current = Test.objects.select_for_update().get(pk=test.pk)
        impact = get_test_delete_impact(current)
        if impact.global_events and not allow_linked_events:
            raise ValueError(
                f"This test is linked to {impact.global_events} guest/global event(s). "
                "Confirm linked-event deletion explicitly before continuing."
            )

        import_job = TestImportJob.objects.filter(published_test=current).first()
        English_Question.objects.filter(test=current).delete()
        Math_Question.objects.filter(test=current).delete()
        current.delete()

        if import_job:
            # The staging data is intentionally preserved. The operator can
            # fix it and publish again instead of rebuilding the entire import.
            import_job.refresh_from_db()
            import_job.published_at = None
            import_job.status = TestImportJob.STATUS_REVIEW_REQUIRED
            import_job.save(update_fields=["published_at", "status", "updated_at"])
            import_job.refresh_review_status()

        return impact
