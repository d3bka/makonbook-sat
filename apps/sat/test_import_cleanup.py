from __future__ import annotations

from dataclasses import dataclass
from threading import Thread
from typing import Iterable

from django.db import transaction
from django.urls import reverse

from .models import MakonNotification, TestImportJob, TestImportQuestion


_LOCKED_STATUSES = {
    TestImportJob.STATUS_QUEUED,
    TestImportJob.STATUS_PROCESSING,
    TestImportJob.STATUS_PUBLISHING,
}


@dataclass(frozen=True)
class ImportDeleteResult:
    job_id: int
    name: str
    question_count: int
    review_count: int
    published_test_name: str


def _file_ref(field):
    name = getattr(field, "name", "") or ""
    storage = getattr(field, "storage", None)
    if not name or storage is None:
        return None
    return storage, name


def _cleanup_files(refs: Iterable[tuple]):
    """Best-effort storage cleanup after the DB transaction commits."""
    seen = set()
    for storage, name in refs:
        key = (id(storage), name)
        if key in seen:
            continue
        seen.add(key)
        try:
            storage.delete(name)
        except Exception:
            # A failed remote-storage cleanup must never resurrect / roll back
            # a staging record that was deliberately deleted from the DB.
            pass


def _schedule_cleanup_files(refs: Iterable[tuple]):
    """Run non-critical R2 deletes off the request path.

    Database deletion is authoritative. Remote file cleanup is best-effort and
    should never make the Manager wait several seconds for sequential network
    calls. A daemon thread is intentionally used here because orphaned files
    are harmless and can be cleaned later, while a blocked admin action is not.
    """
    refs = tuple(refs)
    if not refs:
        return
    Thread(
        target=_cleanup_files,
        args=(refs,),
        name="makonbook-test-import-file-cleanup",
        daemon=True,
    ).start()


def delete_import_job(job_id: int) -> ImportDeleteResult:
    """
    Delete an import/staging job without deleting a published MakonBook Test.

    Questions/reviews are CASCADE children and disappear with the job. Source
    PDFs are removed from storage. Staging question images are removed only
    when no published Test points at this import, because the published
    questions currently reuse the same underlying image file names.
    """
    with transaction.atomic():
        # Lock only the TestImportJob row itself. Do NOT combine
        # select_for_update() with select_related("published_test") here:
        # published_test is nullable, so Django generates a LEFT OUTER JOIN
        # and PostgreSQL rejects FOR UPDATE on the nullable side of that join.
        # We only use published_test_id below, which is already stored on the
        # TestImportJob row and requires no join at all.
        job = (
            TestImportJob.objects
            .select_for_update()
            .get(pk=job_id)
        )
        if job.status in _LOCKED_STATUSES:
            raise ValueError(
                "This import is currently queued, processing, or publishing. "
                "Wait for the background task to finish before deleting it."
            )

        name = job.name
        published_test_name = job.published_test_id or ""
        question_count = job.questions.count()
        review_count = job.reviews.count()
        refs = []

        # PDFs belong exclusively to the staging import and can always go.
        for field_name in ("source_pdf", "answer_pdf", "english_pdf", "math_pdf"):
            ref = _file_ref(getattr(job, field_name, None))
            if ref:
                refs.append(ref)

        # A published Test currently reuses these image paths, so preserve the
        # files if this staging job has already produced a live test.
        if not job.published_test_id:
            image_fields = ("image", "image_a", "image_b", "image_c", "image_d")
            storages = {
                field_name: TestImportQuestion._meta.get_field(field_name).storage
                for field_name in image_fields
            }
            for row in job.questions.values_list(*image_fields).iterator(chunk_size=500):
                for field_name, file_name in zip(image_fields, row):
                    if file_name:
                        refs.append((storages[field_name], str(file_name)))

        detail_url = reverse("test_import_detail", args=[job.pk])
        MakonNotification.objects.filter(url=detail_url).delete()

        result = ImportDeleteResult(
            job_id=job.pk,
            name=name,
            question_count=question_count,
            review_count=review_count,
            published_test_name=published_test_name,
        )
        job.delete()
        transaction.on_commit(lambda refs=tuple(refs): _schedule_cleanup_files(refs))
        return result
