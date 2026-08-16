from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import FileResponse, HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.views.decorators.clickjacking import xframe_options_sameorigin
from datetime import timedelta

from .models import MakonNotification, TestImportJob, TestImportQuestion, TestImportReview
from .test_import_forms import TestImportQuestionForm, TestImportUploadForm
from .test_import_service import publish_import_job, validate_job
from .tasks import enqueue_test_import
from .roles import is_support_teacher


def _manager_allowed(user):
    return bool(
        user.is_authenticated
        and (
            user.is_superuser
            or user.is_staff
            or user.groups.filter(name__iexact="Admin").exists()
            or user.groups.filter(name__iexact="Manager").exists()
        )
    )


def _reviewer_allowed(user, job):
    return bool(is_support_teacher(user) and job.reviews.filter(reviewer=user).exists())


def _job_allowed(user, job):
    return _manager_allowed(user) or _reviewer_allowed(user, job)


@login_required(login_url="/login/")
def test_import_list(request):
    if _manager_allowed(request.user):
        jobs = TestImportJob.objects.select_related("created_by", "published_test").all()
    elif is_support_teacher(request.user):
        jobs = TestImportJob.objects.filter(reviews__reviewer=request.user).select_related("created_by", "published_test").distinct()
    else:
        return HttpResponseForbidden("Test review access required.")
    pending_count = TestImportReview.objects.filter(reviewer=request.user, verdict=TestImportReview.VERDICT_PENDING).count()
    return render(request, "sat/test_import/list.html", {"jobs": jobs, "can_create": _manager_allowed(request.user), "pending_count": pending_count})


@login_required(login_url="/login/")
def test_import_create(request):
    if not _manager_allowed(request.user):
        return HttpResponseForbidden("Manager access required.")
    form = TestImportUploadForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        job = form.save(commit=False)
        job.created_by = request.user
        job.status = TestImportJob.STATUS_UPLOADED
        job.save()
        try:
            enqueue_test_import(job.pk, run_audit=True)
            messages.success(request, "Structured PDF uploaded. MakonBook parsing was queued in the background.")
        except Exception as exc:
            messages.error(request, str(exc))
        return redirect("test_import_detail", job_id=job.pk)
    return render(request, "sat/test_import/create.html", {"form": form})


@login_required(login_url="/login/")
def test_import_detail(request, job_id):
    job = get_object_or_404(TestImportJob.objects.select_related("created_by", "published_test"), pk=job_id)
    if not _job_allowed(request.user, job):
        return HttpResponseForbidden("Test review access required.")
    MakonNotification.objects.filter(user=request.user, type=MakonNotification.TYPE_TEST_REVIEW, url=reverse("test_import_detail", args=[job.pk])).update(is_read=True)
    questions = list(job.questions.all())
    grouped = {}
    for question in questions:
        grouped.setdefault((question.section, question.module), []).append(question)
    reviews = list(job.reviews.select_related("reviewer", "reviewer__support_teacher_profile").all())
    my_review = next((item for item in reviews if item.reviewer_id == request.user.id), None)
    validation_counts = {
        "ok": sum(1 for q in questions if q.validation_status == "ok"),
        "warning": sum(1 for q in questions if q.validation_status == "warning"),
        "error": sum(1 for q in questions if q.validation_status == "error"),
    }
    return render(request, "sat/test_import/detail.html", {
        "job": job,
        "question_groups": list(grouped.items()),
        "questions": questions,
        "reviews": reviews,
        "my_review": my_review,
        "validation_counts": validation_counts,
        "can_manage": _manager_allowed(request.user),
        "can_publish": _manager_allowed(request.user) and job.status == TestImportJob.STATUS_READY_TO_PUBLISH and not job.has_blocking_errors,
    })


@login_required(login_url="/login/")
@require_POST
def test_import_process(request, job_id):
    if not _manager_allowed(request.user):
        return HttpResponseForbidden("Manager access required.")
    job = get_object_or_404(TestImportJob, pk=job_id)
    if job.status in {TestImportJob.STATUS_PUBLISHED, TestImportJob.STATUS_PUBLISHING}:
        messages.error(request, "A published import cannot be processed again.")
        return redirect("test_import_detail", job_id=job.pk)
    if job.status in {TestImportJob.STATUS_QUEUED, TestImportJob.STATUS_PROCESSING}:
        messages.info(request, "This import is already queued or processing.")
        return redirect("test_import_detail", job_id=job.pk)
    try:
        enqueue_test_import(job.pk, run_audit=request.POST.get("skip_audit") != "1")
        messages.success(request, "Structured import queued. You can leave this page while the worker processes it.")
    except Exception as exc:
        messages.error(request, str(exc))
    return redirect("test_import_detail", job_id=job.pk)


@login_required(login_url="/login/")
def test_import_status(request, job_id):
    job = get_object_or_404(TestImportJob, pk=job_id)
    if not _job_allowed(request.user, job):
        return JsonResponse({"detail": "Test review access required."}, status=403)

    now = timezone.now()
    stalled = False
    worker_warning = ""
    if job.status == TestImportJob.STATUS_QUEUED and job.queued_at and now - job.queued_at > timedelta(minutes=2):
        stalled = True
        worker_warning = "The task is still queued. The Celery worker may be offline; the queued job will start when the worker returns."
    elif job.status == TestImportJob.STATUS_PROCESSING and job.processing_heartbeat_at and now - job.processing_heartbeat_at > timedelta(minutes=5):
        stalled = True
        worker_warning = "No progress heartbeat for more than 5 minutes. Check the Celery worker logs before retrying."

    return JsonResponse({
        "id": job.pk,
        "status": job.status,
        "status_label": job.get_status_display(),
        "percent": max(0, min(100, int(job.progress_percent or 0))),
        "stage": job.progress_stage or "",
        "message": job.progress_message or "",
        "error": job.error_message or "",
        "question_count": job.questions.count(),
        "stalled": stalled,
        "worker_warning": worker_warning,
        "terminal": job.status not in {TestImportJob.STATUS_QUEUED, TestImportJob.STATUS_PROCESSING},
        "log": list(job.processing_log or [])[-12:],
    })


@login_required(login_url="/login/")
def test_import_question_edit(request, job_id, question_id):
    job = get_object_or_404(TestImportJob, pk=job_id)
    if not _job_allowed(request.user, job):
        return HttpResponseForbidden("Test review access required.")
    question = get_object_or_404(TestImportQuestion, pk=question_id, job=job)
    if job.status in {TestImportJob.STATUS_QUEUED, TestImportJob.STATUS_PROCESSING}:
        return HttpResponseForbidden("This staging import is locked while background processing is running.")
    if job.status == TestImportJob.STATUS_PUBLISHED:
        return HttpResponseForbidden("Published staging questions are read-only.")
    form = TestImportQuestionForm(request.POST or None, request.FILES or None, instance=question)
    if request.method == "POST" and form.is_valid():
        form.save()
        job.reviews.update(verdict=TestImportReview.VERDICT_PENDING, note="", reviewed_at=None)
        validate_job(job)
        job.status = TestImportJob.STATUS_REVIEW_REQUIRED if not job.has_blocking_errors else TestImportJob.STATUS_CHANGES_REQUESTED
        job.save(update_fields=["status", "updated_at"])
        messages.success(request, f"{question.display_code} updated. Previous approvals were reset because the test changed.")
        return redirect("test_import_detail", job_id=job.pk)
    return render(request, "sat/test_import/question_form.html", {"job": job, "question": question, "form": form})


@login_required(login_url="/login/")
@require_POST
def test_import_review(request, job_id):
    job = get_object_or_404(TestImportJob, pk=job_id)
    if job.status in {TestImportJob.STATUS_QUEUED, TestImportJob.STATUS_PROCESSING}:
        messages.error(request, "Wait for background processing to finish before reviewing this import.")
        return redirect("test_import_detail", job_id=job.pk)
    review = job.reviews.filter(reviewer=request.user).first()
    if not _manager_allowed(request.user) and not is_support_teacher(request.user):
        return HttpResponseForbidden("Support Teacher group membership is required to review tests.")
    if not review and not _manager_allowed(request.user):
        return HttpResponseForbidden("You are not assigned to review this import.")
    if not review:
        review, _ = TestImportReview.objects.get_or_create(job=job, reviewer=request.user)
    verdict = request.POST.get("verdict")
    if verdict not in {TestImportReview.VERDICT_APPROVED, TestImportReview.VERDICT_CHANGES}:
        messages.error(request, "Invalid review action.")
        return redirect("test_import_detail", job_id=job.pk)
    if verdict == TestImportReview.VERDICT_APPROVED and job.has_blocking_errors:
        messages.error(request, "This test still has blocking validation errors and cannot be approved.")
        return redirect("test_import_detail", job_id=job.pk)
    note = (request.POST.get("note") or "").strip()[:3000]
    if verdict == TestImportReview.VERDICT_CHANGES and not note:
        messages.error(request, "Explain what needs to be changed.")
        return redirect("test_import_detail", job_id=job.pk)
    review.verdict = verdict
    review.note = note
    review.reviewed_at = timezone.now()
    review.save(update_fields=["verdict", "note", "reviewed_at", "updated_at"])
    job.refresh_review_status()
    messages.success(request, "Review saved.")
    return redirect("test_import_detail", job_id=job.pk)


@login_required(login_url="/login/")
@require_POST
def test_import_publish(request, job_id):
    if not _manager_allowed(request.user):
        return HttpResponseForbidden("Manager access required.")
    job = get_object_or_404(TestImportJob, pk=job_id)
    try:
        test = publish_import_job(job.pk, published_by=request.user)
        messages.success(request, f"{test.name} is published and visible according to existing access rules.")
    except Exception as exc:
        messages.error(request, f"Could not publish: {exc}")
    return redirect("test_import_detail", job_id=job.pk)


@login_required(login_url="/login/")
@xframe_options_sameorigin
def test_import_pdf(request, job_id):
    job = get_object_or_404(TestImportJob, pk=job_id)
    if not _job_allowed(request.user, job):
        return HttpResponseForbidden("Test review access required.")

    requested_section = (request.GET.get("section") or "").strip().lower()
    field = None
    label = "source"
    if requested_section in {"english", "ebrw"} and job.english_pdf:
        field, label = job.english_pdf, "EBRW"
    elif requested_section == "math" and job.math_pdf:
        field, label = job.math_pdf, "Math"
    elif job.english_pdf:
        field, label = job.english_pdf, "EBRW"
    elif job.math_pdf:
        field, label = job.math_pdf, "Math"
    elif job.source_pdf:
        field, label = job.source_pdf, "source"

    if not field:
        return HttpResponseForbidden("No source PDF is attached to this import.")
    field.open("rb")
    return FileResponse(field, content_type="application/pdf", filename=f"{job.name}-{label}.pdf")


@login_required(login_url="/login/")
@require_POST
def test_import_notifications_read(request):
    MakonNotification.objects.filter(user=request.user, is_read=False).update(is_read=True)
    return JsonResponse({"ok": True, "unread": 0})
