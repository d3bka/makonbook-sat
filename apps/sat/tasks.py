import os
import subprocess
import uuid

import boto3
from celery import shared_task
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import BaseVideo as Video, TestImportJob


@shared_task
def convert_video_to_hls(video_id):
    """Convert an uploaded MP4 video to HLS (.m3u8) and upload to Cloudflare R2."""
    video = Video.objects.get(id=video_id)
    video.conversion_status = "converting"
    video.save(update_fields=["conversion_status"])

    try:
        local_mp4_path = video.video_file.path
        local_hls_path = local_mp4_path.replace(".mp4", ".m3u8")

        ffmpeg_cmd = [
            "ffmpeg", "-i", local_mp4_path, "-codec:", "copy",
            "-start_number", "0", "-hls_time", "10", "-hls_list_size", "0",
            "-f", "hls", local_hls_path,
        ]
        subprocess.run(ffmpeg_cmd, check=True)

        s3_client = boto3.client(
            "s3",
            endpoint_url=settings.AWS_S3_ENDPOINT_URL,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        )
        s3_client.upload_file(
            local_hls_path,
            settings.AWS_STORAGE_BUCKET_NAME,
            f"videos/hls/{os.path.basename(local_hls_path)}",
        )
        for ts_file in os.listdir(os.path.dirname(local_hls_path)):
            if ts_file.endswith(".ts"):
                s3_client.upload_file(
                    os.path.join(os.path.dirname(local_hls_path), ts_file),
                    settings.AWS_STORAGE_BUCKET_NAME,
                    f"videos/hls/{ts_file}",
                )

        video.hls_url = (
            f"{settings.AWS_S3_ENDPOINT_URL}/{settings.AWS_STORAGE_BUCKET_NAME}/"
            f"videos/hls/{os.path.basename(local_hls_path)}"
        )
        video.conversion_status = "completed"
        video.save(update_fields=["hls_url", "conversion_status"])

        os.remove(local_mp4_path)
        os.remove(local_hls_path)
    except Exception:
        video.conversion_status = "failed"
        video.save(update_fields=["conversion_status"])
        raise


@shared_task(
    bind=True,
    name="sat.process_test_import",
    acks_late=True,
    reject_on_worker_lost=True,
    soft_time_limit=getattr(settings, "TEST_IMPORT_CELERY_SOFT_TIME_LIMIT", 3300),
    time_limit=getattr(settings, "TEST_IMPORT_CELERY_TIME_LIMIT", 3600),
)
def process_test_import_task(self, job_id, run_audit=True):
    """Run structured test import outside Gunicorn and mirror progress to Celery task state."""
    from .test_import_service import process_import_job

    job = TestImportJob.objects.get(pk=job_id)
    request_id = self.request.id or ""
    if job.celery_task_id and request_id and job.celery_task_id != request_id:
        return {"job_id": job_id, "status": "superseded", "percent": job.progress_percent}
    TestImportJob.objects.filter(pk=job_id).update(
        celery_task_id=request_id,
        processing_heartbeat_at=timezone.now(),
    )

    def progress(percent, stage, message):
        self.update_state(
            state="PROGRESS",
            meta={"percent": percent, "stage": stage, "message": message, "job_id": job_id},
        )

    job = process_import_job(job_id, run_audit=run_audit, progress_callback=progress)
    return {
        "job_id": job.pk,
        "status": job.status,
        "percent": job.progress_percent,
        "stage": job.progress_stage,
    }


def enqueue_test_import(job_id, *, run_audit=True):
    """Persist a queue state first, then send the task. Broker failures become visible/retryable."""
    task_id = str(uuid.uuid4())
    now = timezone.now()
    with transaction.atomic():
        job = TestImportJob.objects.select_for_update().get(pk=job_id)
        if job.status in {TestImportJob.STATUS_QUEUED, TestImportJob.STATUS_PROCESSING}:
            raise RuntimeError("This import is already queued or processing.")
        if job.status in {TestImportJob.STATUS_PUBLISHED, TestImportJob.STATUS_PUBLISHING}:
            raise RuntimeError("A published import cannot be processed again.")

        # A re-run invalidates prior human decisions before the new worker starts.
        job.reviews.update(verdict="pending", note="", reviewed_at=None)
        job.status = TestImportJob.STATUS_QUEUED
        job.celery_task_id = task_id
        job.progress_percent = 1
        job.progress_stage = "queued"
        job.progress_message = "Waiting for the structured import worker..."
        job.queued_at = now
        job.processing_started_at = None
        job.processing_heartbeat_at = now
        job.error_message = ""
        job.save(update_fields=[
            "status", "celery_task_id", "progress_percent", "progress_stage", "progress_message",
            "queued_at", "processing_started_at", "processing_heartbeat_at", "error_message", "updated_at",
        ])

    try:
        process_test_import_task.apply_async(
            args=[job.pk],
            kwargs={"run_audit": bool(run_audit)},
            task_id=task_id,
        )
    except Exception as exc:
        job.status = TestImportJob.STATUS_FAILED
        job.progress_stage = "queue_failed"
        job.progress_message = "Could not reach the background worker queue."
        job.error_message = f"Could not queue import: {exc}"
        job.processing_heartbeat_at = timezone.now()
        job.save(update_fields=[
            "status", "progress_stage", "progress_message", "error_message",
            "processing_heartbeat_at", "updated_at",
        ])
        raise RuntimeError(
            "Could not queue the import. Check Redis/Celery and try again."
        ) from exc
    return task_id

