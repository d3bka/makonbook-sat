from django.contrib import messages
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import FileResponse, HttpResponseForbidden, JsonResponse
from django.db import transaction
from django.db.models import Count, Exists, IntegerField, OuterRef, Q, Subquery, Value
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.views.decorators.clickjacking import xframe_options_sameorigin

from .models import English_Question, MakonNotification, Math_Question, Test, TestImportJob, TestImportQuestion, TestImportReview
from .test_import_forms import TestImportQuestionForm, TestImportUploadForm
from .test_management_forms import ManagedEnglishQuestionForm, ManagedMathQuestionForm, ManagedTestForm
from .test_import_service import (
    audit_staging_question_batch,
    process_import_job,
    publish_import_job,
    validate_job,
)
from .roles import is_support_teacher
from .test_import_rate_limit import check_test_import_submit_limit
from .test_management_service import (
    delete_published_test,
    get_test_delete_impact,
    set_test_availability,
    update_test_settings,
)
from .test_import_cleanup import delete_import_job


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


def _wants_json(request):
    """Return True for progressive-enhancement AJAX actions."""
    return (
        request.headers.get("x-requested-with") == "XMLHttpRequest"
        or "application/json" in (request.headers.get("accept") or "")
    )


def _annotate_import_queue(queryset):
    """Attach queue-card counters in one SQL query instead of N+1 lookups."""
    return queryset.annotate(
        ui_question_count=Count("questions", distinct=True),
        ui_reviewer_count=Count("reviews", distinct=True),
        ui_approval_count=Count(
            "reviews",
            filter=Q(reviews__verdict=TestImportReview.VERDICT_APPROVED),
            distinct=True,
        ),
    )


def _prepare_import_queue_rows(queryset):
    rows = list(_annotate_import_queue(queryset))
    for job in rows:
        reviewers = int(getattr(job, "ui_reviewer_count", 0) or 0)
        required = int(job.required_approvals or 0)
        job.ui_approval_target = min(required, reviewers) if reviewers > 0 else required
    return rows


def _reviewer_allowed(user, job):
    return bool(is_support_teacher(user) and job.reviews.filter(reviewer=user).exists())


def _job_allowed(user, job):
    return _manager_allowed(user) or _reviewer_allowed(user, job)


def _recover_stale_local_processing(job, *, stale_after_seconds=300):
    """Recover a row left PROCESSING after an interrupted synchronous request."""
    if job.status != TestImportJob.STATUS_PROCESSING:
        return False
    heartbeat = job.processing_heartbeat_at or job.processing_started_at or job.updated_at
    if not heartbeat or (timezone.now() - heartbeat).total_seconds() < stale_after_seconds:
        return False
    job.status = TestImportJob.STATUS_FAILED
    job.progress_stage = "interrupted"
    job.progress_message = "Previous local parsing was interrupted. It is safe to run the parser again."
    job.error_message = "Previous local parsing did not finish. Re-run the parser from this page."
    job.save(update_fields=[
        "status", "progress_stage", "progress_message", "error_message", "updated_at",
    ])
    return True


@login_required(login_url="/login/")
def test_import_list(request):
    # This screen is a staging/publishing queue, not an archive of imports that
    # are already live. Published staging records remain in the DB for audit
    # history but are intentionally hidden from the queue.
    can_manage = _manager_allowed(request.user)
    if can_manage:
        jobs_qs = (
            TestImportJob.objects
            .select_related("created_by", "published_test")
            .exclude(status=TestImportJob.STATUS_PUBLISHED)
        )
    elif is_support_teacher(request.user):
        jobs_qs = (
            TestImportJob.objects
            .filter(reviews__reviewer=request.user)
            .exclude(status=TestImportJob.STATUS_PUBLISHED)
            .select_related("created_by", "published_test")
            .distinct()
        )
    else:
        return HttpResponseForbidden("Test review access required.")

    jobs = _prepare_import_queue_rows(jobs_qs)
    pending_count = TestImportReview.objects.filter(
        reviewer=request.user,
        verdict=TestImportReview.VERDICT_PENDING,
        job__status__in=[
            TestImportJob.STATUS_REVIEW_REQUIRED,
            TestImportJob.STATUS_CHANGES_REQUESTED,
            TestImportJob.STATUS_READY_TO_PUBLISH,
        ],
    ).count()
    failed_count = sum(1 for job in jobs if job.status == TestImportJob.STATUS_FAILED) if can_manage else 0
    return render(request, "sat/test_import/list.html", {
        "jobs": jobs,
        "can_create": can_manage,
        "can_manage": can_manage,
        "pending_count": pending_count,
        "failed_count": failed_count,
    })



@login_required(login_url="/login/")
def managed_test_list(request):
    if not _manager_allowed(request.user):
        return HttpResponseForbidden("Manager access required.")

    english_count_sq = (
        English_Question.objects
        .filter(test_id=OuterRef("pk"))
        .values("test_id")
        .annotate(total=Count("pk"))
        .values("total")[:1]
    )
    math_count_sq = (
        Math_Question.objects
        .filter(test_id=OuterRef("pk"))
        .values("test_id")
        .annotate(total=Count("pk"))
        .values("total")[:1]
    )
    imported_sq = TestImportJob.objects.filter(published_test_id=OuterRef("pk"))

    # Important: this is a read-only listing page. Never create/upload default
    # icons from GET; that used to turn a simple page load into serial R2 writes.
    tests = list(
        Test.objects
        .prefetch_related("groups")
        .annotate(
            english_count=Coalesce(
                Subquery(english_count_sq, output_field=IntegerField()),
                Value(0),
            ),
            math_count=Coalesce(
                Subquery(math_count_sq, output_field=IntegerField()),
                Value(0),
            ),
            has_import_source=Exists(imported_sq),
        )
        .order_by("-published_at", "-created", "name")
    )
    for test in tests:
        test.total_question_count = int(test.english_count or 0) + int(test.math_count or 0)
        test.group_count = len(test.groups.all())

    return render(request, "sat/test_import/published_list.html", {"tests": tests})


@login_required(login_url="/login/")
@require_POST
def managed_test_toggle_availability(request, test_name):
    if not _manager_allowed(request.user):
        return HttpResponseForbidden("Manager access required.")

    test = get_object_or_404(Test, pk=test_name)
    requested = str(request.POST.get("state") or "").strip().lower()
    if requested not in {"open", "closed"}:
        if _wants_json(request):
            return JsonResponse({"ok": False, "error": "Invalid test availability state."}, status=400)
        messages.error(request, "Invalid test availability state.")
        return redirect("managed_test_list")

    is_available = requested == "open"
    set_test_availability(test, is_available=is_available)
    message = (
        f"{test.name} is open across MakonBook again."
        if is_available
        else (
            f"{test.name} is closed across normal MakonBook access, including all Classroom attempts. "
            "Guest Mode remains available and existing history/progress is preserved."
        )
    )
    if _wants_json(request):
        return JsonResponse({
            "ok": True,
            "test_name": test.name,
            "is_available": is_available,
            "message": message,
        })

    if is_available:
        messages.success(request, message)
    else:
        messages.warning(request, message)
    if request.POST.get("return_to") == "edit":
        return redirect("managed_test_edit", test_name=test.pk)
    return redirect("managed_test_list")


@login_required(login_url="/login/")
def managed_test_edit(request, test_name):
    if not _manager_allowed(request.user):
        return HttpResponseForbidden("Manager access required.")
    test = get_object_or_404(Test.objects.prefetch_related("groups"), pk=test_name)
    form = ManagedTestForm(request.POST or None, request.FILES or None, test=test)
    if request.method == "POST" and form.is_valid():
        try:
            test = update_test_settings(
                test,
                name=form.cleaned_data["name"],
                groups=form.cleaned_data["groups"],
                is_available=form.cleaned_data["is_available"],
                icon=form.cleaned_data.get("icon"),
                remove_icon=bool(form.cleaned_data.get("remove_icon")),
            )
            messages.success(request, "Published test settings were updated.")
            return redirect("managed_test_edit", test_name=test.pk)
        except Exception as exc:
            form.add_error(None, str(exc))

    english = list(English_Question.objects.filter(test=test).order_by("module", "number", "pk"))
    math = list(Math_Question.objects.filter(test=test).order_by("module", "number", "pk"))
    grouped = [
        ("Reading & Writing · Module 1", [q for q in english if q.module == "module_1"], "english"),
        ("Reading & Writing · Module 2", [q for q in english if q.module == "module_2"], "english"),
        ("Math · Module 1", [q for q in math if q.module == "module_1"], "math"),
        ("Math · Module 2", [q for q in math if q.module == "module_2"], "math"),
    ]
    grouped = [row for row in grouped if row[1]]
    return render(request, "sat/test_import/published_edit.html", {
        "test": test,
        "form": form,
        "question_groups": grouped,
        "english_count": len(english),
        "math_count": len(math),
    })


@login_required(login_url="/login/")
def managed_test_question_edit(request, test_name, section, question_id):
    if not _manager_allowed(request.user):
        return HttpResponseForbidden("Manager access required.")
    test = get_object_or_404(Test, pk=test_name)
    if section == "english":
        question = get_object_or_404(English_Question, pk=question_id, test=test)
        form_class = ManagedEnglishQuestionForm
        section_label = "Reading & Writing"
    elif section == "math":
        question = get_object_or_404(Math_Question, pk=question_id, test=test)
        form_class = ManagedMathQuestionForm
        section_label = "Math"
    else:
        return HttpResponseForbidden("Invalid test section.")

    form = form_class(request.POST or None, request.FILES or None, instance=question)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, f"{section_label} question #{question.number} was updated.")
        return redirect("managed_test_edit", test_name=test.pk)
    return render(request, "sat/test_import/published_question_form.html", {
        "test": test,
        "question": question,
        "form": form,
        "section": section,
        "section_label": section_label,
    })


@login_required(login_url="/login/")
def managed_test_delete(request, test_name):
    if not _manager_allowed(request.user):
        return HttpResponseForbidden("Manager access required.")
    test = get_object_or_404(Test, pk=test_name)
    impact = None
    error = ""
    if request.method == "POST":
        typed_name = (request.POST.get("confirm_name") or "").strip()
        typed_word = (request.POST.get("confirm_word") or "").strip().upper()
        allow_linked_events = request.POST.get("delete_linked_events") == "1"
        if typed_name != test.name:
            error = "Type the exact test name to confirm deletion."
        elif typed_word != "DELETE":
            error = "Type DELETE in the confirmation field."
        else:
            try:
                deleted_impact = delete_published_test(test, allow_linked_events=allow_linked_events)
                message = (
                    f"Test '{test_name}' was deleted with "
                    f"{deleted_impact.total_questions} published question(s). "
                    "Staging data was preserved when available."
                )
                if _wants_json(request):
                    return JsonResponse({
                        "ok": True,
                        "redirect_url": reverse("managed_test_list"),
                        "message": message,
                    })
                messages.success(request, message)
                return redirect("managed_test_list")
            except Exception as exc:
                error = str(exc)
                if _wants_json(request):
                    return JsonResponse({"ok": False, "error": error}, status=409)

    if impact is None:
        impact = get_test_delete_impact(test)
    return render(request, "sat/test_import/published_delete.html", {
        "test": test,
        "impact": impact,
        "error": error,
    })

@login_required(login_url="/login/")
@require_POST
def test_import_delete(request, job_id):
    if not _manager_allowed(request.user):
        return HttpResponseForbidden("Manager access required.")
    try:
        result = delete_import_job(job_id)
        if result.published_test_name:
            message = (
                f"Staging import '{result.name}' was deleted. "
                f"Published test '{result.published_test_name}' was kept intact."
            )
        else:
            message = f"Draft '{result.name}' was deleted with {result.question_count} staging question(s)."
        if _wants_json(request):
            return JsonResponse({
                "ok": True,
                "job_id": result.job_id,
                "message": message,
            })
        messages.success(request, message)
    except Exception as exc:
        message = f"Could not delete staging import: {exc}"
        if _wants_json(request):
            return JsonResponse({"ok": False, "error": message}, status=409)
        messages.error(request, message)
    return redirect("test_import_list")


@login_required(login_url="/login/")
@require_POST
def test_import_clear_failed(request):
    if not _manager_allowed(request.user):
        return HttpResponseForbidden("Manager access required.")

    # Only FAILED jobs are bulk-cleaned. CHANGES REQUESTED / REVIEW REQUIRED
    # may contain valuable work and must still be deleted explicitly.
    job_ids = list(
        TestImportJob.objects
        .filter(status=TestImportJob.STATUS_FAILED)
        .values_list("pk", flat=True)
    )
    deleted = 0
    skipped = 0
    for job_id in job_ids:
        try:
            delete_import_job(job_id)
            deleted += 1
        except TestImportJob.DoesNotExist:
            continue
        except Exception:
            skipped += 1

    if _wants_json(request):
        return JsonResponse({
            "ok": True,
            "deleted": deleted,
            "skipped": skipped,
            "message": (
                f"Deleted {deleted} failed staging import(s)."
                if deleted
                else "There are no failed staging imports to clean up."
            ),
        })
    if deleted:
        messages.success(request, f"Deleted {deleted} failed staging import(s).")
    if skipped:
        messages.warning(request, f"Skipped {skipped} import(s) that could not be safely deleted.")
    if not deleted and not skipped:
        messages.info(request, "There are no failed staging imports to clean up.")
    return redirect("test_import_list")


@login_required(login_url="/login/")
def test_import_create(request):
    if not _manager_allowed(request.user):
        return HttpResponseForbidden("Manager access required.")
    form = TestImportUploadForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        # Server-side duplicate protection remains authoritative even though the
        # upload button is also locked in JavaScript. A second concurrent POST
        # sees the first request's PROCESSING row and is redirected to it.
        active_job = (
            TestImportJob.objects
            .filter(created_by=request.user, status=TestImportJob.STATUS_PROCESSING)
            .order_by("-created_at")
            .first()
        )
        if active_job and _recover_stale_local_processing(active_job):
            active_job = None
        if active_job:
            messages.info(request, "You already have a structured import processing. Opened it instead of creating a duplicate.")
            return redirect("test_import_detail", job_id=active_job.pk)

        submit_limit = check_test_import_submit_limit(request)
        if not submit_limit.allowed:
            if submit_limit.scope == "cooldown":
                text = f"Please wait {submit_limit.retry_after} seconds before submitting another test import."
            else:
                text = "Too many test-import submissions. Wait a few minutes before trying again."
            form.add_error(None, text)
            response = render(request, "sat/test_import/create.html", {"form": form})
            response.status_code = 429
            response["Retry-After"] = str(max(1, submit_limit.retry_after))
            return response

        job = form.save(commit=False)
        job.created_by = request.user
        job.status = TestImportJob.STATUS_UPLOADED
        job.save()
        job.refresh_from_db(fields=["english_pdf", "math_pdf", "source_pdf", "status"])
        has_structured_pdf = bool(
            getattr(job.english_pdf, "name", "")
            or getattr(job.math_pdf, "name", "")
        )
        if not has_structured_pdf:
            job.status = TestImportJob.STATUS_FAILED
            job.error_message = "The structured PDF filenames were not persisted. Please upload the files again."
            job.save(update_fields=["status", "error_message", "updated_at"])
            messages.error(request, job.error_message)
            return redirect("test_import_detail", job_id=job.pk)

        try:
            # Structured v2 parsing is deterministic and fast enough to run in
            # this request. No Redis broker or Celery worker is involved. AI
            # audit is deliberately separate/optional on the review screen.
            process_import_job(job.pk, run_audit=False)
            messages.success(request, "Structured PDFs parsed locally. The staging test is ready for review.")
        except Exception as exc:
            messages.error(request, f"Structured import failed: {exc}")
        return redirect("test_import_detail", job_id=job.pk)
    return render(request, "sat/test_import/create.html", {"form": form})


def _import_file_url(field):
    try:
        return field.url if field else ""
    except (ValueError, AttributeError):
        return ""


@login_required(login_url="/login/")
def test_import_preview(request, job_id):
    """Read-only, untimed reviewer preview that mirrors the live SAT test UI.

    Nothing in this view creates an attempt, writes an answer, starts a timer,
    or changes staging data. Reviewer selections live only in browser memory.
    """
    job = get_object_or_404(TestImportJob.objects.select_related("created_by"), pk=job_id)
    if not _job_allowed(request.user, job):
        return HttpResponseForbidden("Test review access required.")

    questions = list(job.questions.all().order_by("section", "module", "number", "pk"))
    if not questions:
        messages.info(request, "This staging import has no questions to preview yet.")
        return redirect("test_import_detail", job_id=job.pk)

    module_order = {
        ("english", "module_1"): 0,
        ("english", "module_2"): 1,
        ("math", "module_1"): 2,
        ("math", "module_2"): 3,
    }
    available_pairs = sorted(
        {(q.section, q.module) for q in questions},
        key=lambda pair: module_order.get(pair, 99),
    )
    module_options = [
        {
            "section": section,
            "module": module,
            "key": f"{section}:{module}",
            "label": f"{'Reading & Writing' if section == 'english' else 'Math'} · Module {'1' if module == 'module_1' else '2'}",
        }
        for section, module in available_pairs
    ]

    payload = []
    for q in questions:
        payload.append({
            "id": q.pk,
            "section": q.section,
            "module": q.module,
            "number": q.number,
            "passage": q.passage or "",
            "question": q.question or "",
            "a": q.a or "",
            "b": q.b or "",
            "c": q.c or "",
            "d": q.d or "",
            "response_type": q.response_type or "multiple_choice",
            "written": bool(q.written),
            "graph": _import_file_url(q.image),
            "choice_graph": bool(q.choice_graph),
            "image_a": _import_file_url(q.image_a),
            "image_b": _import_file_url(q.image_b),
            "image_c": _import_file_url(q.image_c),
            "image_d": _import_file_url(q.image_d),
            "validation_status": q.validation_status or "ok",
            "validation_errors": list(q.validation_errors or []),
            "source_page": q.source_page or 1,
            # Included for reviewer-only optional answer-key reveal. It is never
            # rendered until the reviewer explicitly asks for it.
            "answer": q.answer or "",
        })

    source_urls = {
        "english": (reverse("test_import_pdf", args=[job.pk]) + "?section=english") if job.english_pdf else "",
        "math": (reverse("test_import_pdf", args=[job.pk]) + "?section=math") if job.math_pdf else "",
    }
    if not source_urls["english"] and not source_urls["math"] and job.source_pdf:
        legacy = reverse("test_import_pdf", args=[job.pk])
        source_urls = {"english": legacy, "math": legacy}

    return render(request, "sat/test_import/preview.html", {
        "job": job,
        "questions_payload": payload,
        "module_options": module_options,
        "source_urls": source_urls,
        "can_manage": _manager_allowed(request.user),
    })


@login_required(login_url="/login/")
def test_import_detail(request, job_id):
    job = get_object_or_404(TestImportJob.objects.select_related("created_by", "published_test"), pk=job_id)
    if _manager_allowed(request.user):
        _recover_stale_local_processing(job)
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
    audited_count = sum(1 for q in questions if q.audit_verdict in {"ok", "issue", "uncertain"})
    audit_issue_count = sum(1 for q in questions if q.audit_verdict == "issue")
    audit_uncertain_count = sum(1 for q in questions if q.audit_verdict == "uncertain")
    audit_complete = bool(questions) and audited_count == len(questions)
    audit_partial = 0 < audited_count < len(questions)
    audit_provider = str(getattr(settings, "QUESTION_AUDIT_PROVIDER", "deepseek") or "deepseek").strip().title()
    audit_model = str(getattr(settings, "TEST_IMPORT_AUDIT_MODEL", "") or getattr(settings, "QUESTION_AUDIT_MODEL", "") or "")
    return render(request, "sat/test_import/detail.html", {
        "job": job,
        "question_groups": list(grouped.items()),
        "questions": questions,
        "reviews": reviews,
        "my_review": my_review,
        "validation_counts": validation_counts,
        "audited_count": audited_count,
        "audit_issue_count": audit_issue_count,
        "audit_uncertain_count": audit_uncertain_count,
        "audit_complete": audit_complete,
        "audit_partial": audit_partial,
        "audit_provider": audit_provider,
        "audit_model": audit_model,
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
    if job.status == TestImportJob.STATUS_PROCESSING and not _recover_stale_local_processing(job):
        messages.info(request, "This import is already processing in another request.")
        return redirect("test_import_detail", job_id=job.pk)
    try:
        process_import_job(job.pk, run_audit=False)
        messages.success(request, "Structured PDFs were re-parsed locally. Previous approvals were reset.")
    except Exception as exc:
        messages.error(request, f"Structured import failed: {exc}")
    return redirect("test_import_detail", job_id=job.pk)


@login_required(login_url="/login/")
def test_import_status(request, job_id):
    # Kept for backward-compatible old browser tabs. Test Import no longer uses
    # a background worker, so this endpoint reports database state only.
    job = get_object_or_404(TestImportJob, pk=job_id)
    if not _job_allowed(request.user, job):
        return JsonResponse({"detail": "Test review access required."}, status=403)
    return JsonResponse({
        "id": job.pk,
        "status": job.status,
        "status_label": job.get_status_display(),
        "percent": max(0, min(100, int(job.progress_percent or 0))),
        "stage": job.progress_stage or "",
        "message": job.progress_message or "",
        "error": job.error_message or "",
        "question_count": job.questions.count(),
        "stalled": False,
        "worker_warning": "",
        "terminal": job.status != TestImportJob.STATUS_PROCESSING,
        "log": list(job.processing_log or [])[-12:],
    })


@login_required(login_url="/login/")
@require_POST
def test_import_audit_batch(request, job_id):
    """Run one optional AI-audit batch directly in this Django request.

    The browser calls this endpoint sequentially, so no Celery/Redis queue or
    result backend is required. The first call resets previous audit findings
    and human approvals; later calls continue with the next unaudited batch.
    """
    if not _manager_allowed(request.user):
        return JsonResponse({"detail": "Manager access required."}, status=403)

    restart = request.POST.get("restart") == "1"
    batch_size = max(1, min(12, int(getattr(settings, "QUESTION_AUDIT_BATCH_SIZE", 8) or 8)))
    now = timezone.now()

    with transaction.atomic():
        job = TestImportJob.objects.select_for_update().get(pk=job_id)
        if job.status in {TestImportJob.STATUS_PUBLISHED, TestImportJob.STATUS_PUBLISHING}:
            return JsonResponse({"detail": "Published staging imports cannot be audited."}, status=409)
        if job.status == TestImportJob.STATUS_PROCESSING:
            return JsonResponse({"detail": "Wait for local PDF parsing to finish first."}, status=409)
        if not job.questions.exists():
            return JsonResponse({"detail": "There are no staging questions to audit."}, status=400)

        # A concurrent double-click must not launch two DeepSeek requests for
        # the same batch. A stale lock is recoverable after two minutes.
        if (
            job.progress_stage == "auditing_batch"
            and job.processing_heartbeat_at
            and (now - job.processing_heartbeat_at).total_seconds() < 120
        ):
            return JsonResponse({"detail": "An AI audit batch is already running."}, status=409)

        if restart:
            job.questions.update(
                audit_verdict="", audit_severity="", audit_confidence=None,
                audit_summary="", audit_verified_answer="", audit_recommended_fix="",
            )
            job.reviews.update(verdict=TestImportReview.VERDICT_PENDING, note="", reviewed_at=None)

        # Recover a batch left in the temporary sentinel state by an interrupted
        # HTTP request, then reserve the next batch before calling the provider.
        job.questions.filter(audit_verdict="auditing").update(audit_verdict="")
        question_ids = list(
            job.questions.filter(audit_verdict="").order_by("section", "module", "number", "pk")
            .values_list("pk", flat=True)[:batch_size]
        )
        total = job.questions.count()
        completed_before = job.questions.filter(audit_verdict__in=["ok", "issue", "uncertain"]).count()

        if not question_ids:
            validate_job(job)
            job.progress_percent = 100
            job.progress_stage = "audit_complete"
            job.progress_message = f"AI audit complete: {completed_before}/{total} questions checked."
            job.processing_heartbeat_at = now
            job.save(update_fields=[
                "progress_percent", "progress_stage", "progress_message",
                "processing_heartbeat_at", "updated_at",
            ])
            job.refresh_review_status()
            return JsonResponse({
                "ok": True, "complete": True, "done": completed_before, "total": total,
                "percent": 100, "message": job.progress_message,
            })

        job.questions.filter(pk__in=question_ids).update(audit_verdict="auditing")
        job.progress_stage = "auditing_batch"
        job.progress_percent = int((completed_before / max(1, total)) * 100)
        job.progress_message = f"Auditing questions {completed_before + 1}-{min(total, completed_before + len(question_ids))} of {total}..."
        job.processing_heartbeat_at = now
        job.save(update_fields=[
            "progress_percent", "progress_stage", "progress_message",
            "processing_heartbeat_at", "updated_at",
        ])

    try:
        audit_staging_question_batch(job, question_ids)
    except Exception as exc:
        TestImportQuestion.objects.filter(job_id=job_id, pk__in=question_ids, audit_verdict="auditing").update(audit_verdict="")
        TestImportJob.objects.filter(pk=job_id).update(
            progress_stage="audit_failed",
            progress_message=f"AI audit failed: {exc}"[:500],
            processing_heartbeat_at=timezone.now(),
        )
        return JsonResponse({"detail": str(exc)}, status=502)

    job = TestImportJob.objects.get(pk=job_id)
    completed = job.questions.filter(audit_verdict__in=["ok", "issue", "uncertain"]).count()
    total = job.questions.count()
    complete = completed >= total
    validate_job(job)
    if complete:
        stage = "audit_complete"
        message = f"AI audit complete: {completed}/{total} questions checked."
        percent = 100
        job.refresh_review_status()
    else:
        stage = "audit_waiting"
        message = f"AI audit progress: {completed}/{total} questions checked."
        percent = int((completed / max(1, total)) * 100)
    job.progress_stage = stage
    job.progress_percent = percent
    job.progress_message = message
    job.processing_heartbeat_at = timezone.now()
    job.save(update_fields=[
        "progress_stage", "progress_percent", "progress_message",
        "processing_heartbeat_at", "updated_at",
    ])
    return JsonResponse({
        "ok": True, "complete": complete, "done": completed, "total": total,
        "percent": percent, "message": message,
    })


@login_required(login_url="/login/")
def test_import_question_edit(request, job_id, question_id):
    job = get_object_or_404(TestImportJob, pk=job_id)
    if not _job_allowed(request.user, job):
        return HttpResponseForbidden("Test review access required.")
    question = get_object_or_404(TestImportQuestion, pk=question_id, job=job)
    if job.status in {TestImportJob.STATUS_QUEUED, TestImportJob.STATUS_PROCESSING}:
        return HttpResponseForbidden("This staging import is locked while local PDF parsing is running.")
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
        messages.error(request, "Wait for local PDF parsing to finish before reviewing this import.")
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
