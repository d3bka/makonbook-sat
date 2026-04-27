from decimal import Decimal

from django.contrib import messages
from django.db import IntegrityError, transaction
from django.db.models import Max, Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import APExamAnswer, APExamAttempt, APExamEvent, APFRQSubmission, APMultipleChoiceQuestion
from apps.sat.models import GuestParticipant


AP_PART_FIELDS = {
    APMultipleChoiceQuestion.PART_A: "part_a_started_at",
    APMultipleChoiceQuestion.PART_B: "part_b_started_at",
    "frq": "frq_started_at",
}


def _event_access_session_key(event):
    return f"ap_event_{event.pk}_secret_ok"


def _is_staff_user(user):
    return bool(user.is_authenticated and (user.is_staff or user.is_superuser))


def _is_secret_unlocked(request, event):
    if not event.requires_secret_code:
        return True
    if _is_staff_user(request.user):
        return True
    return bool(request.session.get(_event_access_session_key(event)))


def _ensure_guest_session(request):
    """Return a stable AP guest key tied to the MakonBook guest participant."""
    if not request.session.session_key:
        request.session.create()
    if not request.session.get("guest_name"):
        request.session["guest_name"] = "Guest"
    request.session["guest_mode"] = True

    guest_id = request.session.get("guest_id")
    if guest_id:
        return f"guest:{guest_id}"
    return f"session:{request.session.session_key or ''}"


def _current_display_name(request, attempt=None):
    if request.user.is_authenticated and not request.session.get("guest_mode"):
        return request.user.get_full_name().strip() or request.user.username

    guest_id = request.session.get("guest_id")
    if guest_id:
        guest = GuestParticipant.objects.filter(guest_id=guest_id).first()
        if guest:
            name = (guest.full_name or "").strip() or "Guest"
            request.session["guest_name"] = name
            return name

    if attempt is not None:
        guest_key = getattr(attempt, "guest_session_key", "") or ""
        if guest_key.startswith("guest:"):
            encoded_guest_id = guest_key.split(":", 1)[1]
            guest = GuestParticipant.objects.filter(guest_id=encoded_guest_id).first()
            if guest:
                return (guest.full_name or "").strip() or "Guest"

        if getattr(attempt, "student_id", None):
            return attempt.student.get_full_name().strip() or attempt.student.username

        stored_guest_name = (getattr(attempt, "guest_name", "") or "").strip()
        if stored_guest_name:
            return stored_guest_name

    return (request.session.get("guest_name") or "Guest").strip() or "Guest"


def _attempt_belongs_to_request(request, attempt):
    if request.session.get("guest_mode"):
        guest_key = _ensure_guest_session(request)
        return bool(attempt.student_id is None and attempt.guest_session_key == guest_key)
    if request.user.is_authenticated:
        return attempt.student_id == request.user.id
    guest_key = _ensure_guest_session(request)
    return bool(attempt.student_id is None and attempt.guest_session_key == guest_key)


def _attempts_for_request(request, event):
    base = APExamAttempt.objects.filter(event=event).order_by("-attempt_number", "-started_at")
    if request.session.get("guest_mode"):
        guest_key = _ensure_guest_session(request)
        return base.filter(student__isnull=True, guest_session_key=guest_key)
    if request.user.is_authenticated:
        return base.filter(student=request.user)
    guest_key = _ensure_guest_session(request)
    return base.filter(student__isnull=True, guest_session_key=guest_key)


def _get_existing_attempt_for_request(request, event):
    return _attempts_for_request(request, event).first()


def _can_start_new_attempt(request, event, attempts=None):
    is_guest_attempt = request.session.get("guest_mode") or not request.user.is_authenticated
    if not _is_staff_user(request.user) and not event.allow_guest_attempts and is_guest_attempt:
        return False
    attempts = attempts if attempts is not None else _attempts_for_request(request, event)
    max_attempts = max(1, int(event.max_attempts or 1))
    return attempts.count() < max_attempts


def _next_attempt_number(attempts):
    current_max = attempts.aggregate(value=Max("attempt_number")).get("value") or 0
    return int(current_max) + 1


def _create_attempt_for_request(request, event):
    attempts = _attempts_for_request(request, event)
    attempt_number = _next_attempt_number(attempts)
    total_questions = event.exam.questions.count()
    defaults = {
        "attempt_number": attempt_number,
        "total_questions": total_questions,
        "last_activity_at": timezone.now(),
    }

    if request.user.is_authenticated and not request.session.get("guest_mode"):
        return APExamAttempt.objects.create(event=event, student=request.user, **defaults)

    guest_session_key = _ensure_guest_session(request)
    return APExamAttempt.objects.create(
        event=event,
        student=None,
        guest_name=_current_display_name(request),
        guest_session_key=guest_session_key,
        **defaults,
    )


def _visible_events_queryset(request):
    qs = APExamEvent.objects.select_related(
        "exam",
        "exam__ap_class",
    ).prefetch_related(
        "exam__groups",
        "classrooms",
    ).filter(is_public=True)

    user = request.user
    if _is_staff_user(user):
        return qs.order_by("-created_at")

    qs = qs.filter(exam__status="published").filter(Q(exam__ap_class__isnull=True) | Q(exam__ap_class__is_active=True))

    if user.is_authenticated:
        user_group_ids = list(user.groups.values_list("id", flat=True))
        return qs.filter(
            Q(is_global=True) |
            Q(classrooms__teacher=user, classrooms__is_active=True, classrooms__classroom_type='ap') |
            Q(
                classrooms__memberships__user=user,
                classrooms__memberships__role="student",
                classrooms__memberships__status="approved",
                classrooms__is_active=True,
                classrooms__classroom_type='ap',
            ) |
            Q(exam__groups__id__in=user_group_ids)
        ).distinct().order_by("-created_at")

    return qs.filter(is_global=True).order_by("-created_at")


def _get_visible_event_or_404(request, slug):
    event = get_object_or_404(
        APExamEvent.objects.select_related("exam", "exam__ap_class").prefetch_related("exam__groups", "classrooms"),
        slug=slug,
    )
    if not event.user_can_see(request.user):
        raise Http404("AP mock exam event not found")
    return event


def ap_event_list_view(request):
    events = _visible_events_queryset(request)
    return render(request, "apclasses/event_list.html", {"events": events})


def ap_event_detail_view(request, slug):
    event = _get_visible_event_or_404(request, slug)
    attempts = _attempts_for_request(request, event)
    existing_attempt = attempts.first()

    if request.method == "POST" and event.requires_secret_code:
        submitted_code = (request.POST.get("access_code") or "").strip()
        if submitted_code == event.access_code:
            request.session[_event_access_session_key(event)] = True
            messages.success(request, "Secret code accepted.")
            return redirect("apclasses:event_detail", slug=slug)
        messages.error(request, "Wrong secret code.")
        return redirect("apclasses:event_detail", slug=slug)

    return render(
        request,
        "apclasses/event_detail.html",
        {
            "event": event,
            "existing_attempt": existing_attempt,
            "attempts": attempts,
            "attempts_used": attempts.count(),
            "attempts_remaining": max(0, int(event.max_attempts or 1) - attempts.count()),
            "can_start_new_attempt": _can_start_new_attempt(request, event, attempts),
            "secret_unlocked": _is_secret_unlocked(request, event),
        },
    )


@require_POST
def start_ap_event_view(request, slug):
    event = _get_visible_event_or_404(request, slug)
    if not event.is_live_now:
        messages.error(request, "This AP mock exam is not live now.")
        return redirect("apclasses:event_detail", slug=slug)
    if not _is_secret_unlocked(request, event):
        messages.error(request, "Enter the secret code before starting this AP mock exam.")
        return redirect("apclasses:event_detail", slug=slug)
    is_guest_attempt = request.session.get("guest_mode") or not request.user.is_authenticated
    if not event.allow_guest_attempts and is_guest_attempt:
        messages.error(request, "Guest attempts are not allowed for this AP mock exam.")
        return redirect("apclasses:event_detail", slug=slug)

    attempts = _attempts_for_request(request, event)
    active_attempt = attempts.filter(status="in_progress").first()
    if active_attempt:
        return redirect("apclasses:attempt", token=active_attempt.token)

    if not _can_start_new_attempt(request, event, attempts):
        latest_attempt = attempts.first()
        messages.error(request, "You have reached the attempt limit for this AP mock exam.")
        if latest_attempt and latest_attempt.status == "submitted":
            return redirect("apclasses:event_result", token=latest_attempt.token)
        return redirect("apclasses:event_detail", slug=slug)

    try:
        with transaction.atomic():
            attempt = _create_attempt_for_request(request, event)
    except IntegrityError:
        # Another tab may have created the same attempt a millisecond earlier.
        attempt = _attempts_for_request(request, event).filter(status="in_progress").first() or _attempts_for_request(request, event).first()

    if not attempt:
        messages.error(request, "Could not start this AP mock exam. Try again.")
        return redirect("apclasses:event_detail", slug=slug)
    if attempt.status == "submitted":
        return redirect("apclasses:event_result", token=attempt.token)
    return redirect("apclasses:attempt", token=attempt.token)


def _ap_part_url(attempt, part, q=1):
    return f"{reverse('apclasses:attempt', args=[attempt.token])}?part={part}&q={q}"


def _get_or_start_ap_part_timer(request, attempt, part):
    field_name = AP_PART_FIELDS.get(part)
    if not field_name:
        return timezone.now()

    started_at = getattr(attempt, field_name, None)
    if started_at:
        return started_at

    started_at = timezone.now()
    setattr(attempt, field_name, started_at)
    attempt.last_activity_at = started_at
    attempt.save(update_fields=[field_name, "last_activity_at"])
    return started_at


def _duration_for_ap_part(event, exam, part):
    if part == APMultipleChoiceQuestion.PART_A:
        return int(getattr(event, "part_a_duration_minutes", None) or getattr(exam, "part_a_duration_minutes", 60) or 60)
    if part == APMultipleChoiceQuestion.PART_B:
        return int(getattr(event, "part_b_duration_minutes", None) or getattr(exam, "part_b_duration_minutes", 45) or 45)
    if part == "frq":
        return int(getattr(event, "frq_duration_minutes", None) or getattr(exam, "frq_duration_minutes", 30) or 30)
    return 60


def _first_available_ap_part(exam):
    if exam.questions.filter(part=APMultipleChoiceQuestion.PART_A).exists():
        return APMultipleChoiceQuestion.PART_A
    if exam.questions.filter(part=APMultipleChoiceQuestion.PART_B).exists():
        return APMultipleChoiceQuestion.PART_B
    if exam.frq_pages.exists():
        return "frq"
    return APMultipleChoiceQuestion.PART_A


def _next_ap_part_after(exam, part):
    if part == APMultipleChoiceQuestion.PART_A:
        if exam.questions.filter(part=APMultipleChoiceQuestion.PART_B).exists():
            return APMultipleChoiceQuestion.PART_B
        if exam.frq_pages.exists():
            return "frq"
    if part == APMultipleChoiceQuestion.PART_B:
        if exam.frq_pages.exists():
            return "frq"
    return None


def _submit_ap_attempt(attempt):
    _recalculate_attempt(attempt)
    attempt.status = "submitted"
    attempt.submitted_at = timezone.now()
    attempt.last_activity_at = attempt.submitted_at
    attempt.save(update_fields=["status", "submitted_at", "last_activity_at", "score", "raw_score", "answered_questions", "total_questions"])
    return attempt


def ap_attempt_view(request, token):
    attempt = get_object_or_404(APExamAttempt.objects.select_related("event", "event__exam", "student"), token=token)
    if not _attempt_belongs_to_request(request, attempt):
        raise Http404("Attempt not found")
    if attempt.status == "submitted":
        return redirect("apclasses:event_result", token=attempt.token)

    exam = attempt.event.exam
    valid_parts = {APMultipleChoiceQuestion.PART_A, APMultipleChoiceQuestion.PART_B, "frq"}
    requested_part = request.GET.get("part") or request.POST.get("part") or _first_available_ap_part(exam)
    if requested_part not in valid_parts:
        requested_part = _first_available_ap_part(exam)

    # Do not allow empty modules to trap students on a blank page.
    if requested_part == APMultipleChoiceQuestion.PART_A and not exam.questions.filter(part=APMultipleChoiceQuestion.PART_A).exists():
        requested_part = _first_available_ap_part(exam)
    if requested_part == APMultipleChoiceQuestion.PART_B and not exam.questions.filter(part=APMultipleChoiceQuestion.PART_B).exists():
        requested_part = "frq" if exam.frq_pages.exists() else _first_available_ap_part(exam)
    if requested_part == "frq" and not exam.frq_pages.exists():
        fallback = _first_available_ap_part(exam)
        if fallback == "frq":
            _submit_ap_attempt(attempt)
            return redirect("apclasses:event_result", token=attempt.token)
        requested_part = fallback

    ordered_questions = []
    frq_pages = []
    current_question = None
    current_frq_page = None

    if requested_part == "frq":
        frq_pages = list(exam.frq_pages.order_by("page_number", "id"))
        total_questions = len(frq_pages)
    else:
        ordered_questions = list(exam.questions.filter(part=requested_part).order_by("number", "id"))
        total_questions = len(ordered_questions)

    current_index = request.GET.get("q", request.POST.get("q", "1"))
    try:
        current_index = int(current_index)
    except ValueError:
        current_index = 1

    if current_index < 1:
        current_index = 1
    if total_questions and current_index > total_questions:
        current_index = total_questions

    if requested_part == "frq":
        current_frq_page = frq_pages[current_index - 1] if frq_pages else None
    else:
        current_question = ordered_questions[current_index - 1] if ordered_questions else None

    if request.method == "POST":
        if requested_part == "frq":
            action = request.POST.get("action")
            if action == "back":
                if current_index > 1:
                    return redirect(_ap_part_url(attempt, "frq", current_index - 1))
                part_b_total = exam.questions.filter(part=APMultipleChoiceQuestion.PART_B).count()
                if part_b_total:
                    return redirect(_ap_part_url(attempt, APMultipleChoiceQuestion.PART_B, part_b_total))
                part_a_total = exam.questions.filter(part=APMultipleChoiceQuestion.PART_A).count()
                if part_a_total:
                    return redirect(_ap_part_url(attempt, APMultipleChoiceQuestion.PART_A, part_a_total))
                return redirect(_ap_part_url(attempt, "frq", current_index))
            if action == "next":
                if current_index < total_questions:
                    return redirect(_ap_part_url(attempt, "frq", current_index + 1))
                _submit_ap_attempt(attempt)
                return redirect("apclasses:event_result", token=attempt.token)
            if action == "goto":
                try:
                    target_index = int(request.POST.get("target_q") or current_index)
                except ValueError:
                    target_index = current_index
                target_index = max(1, min(total_questions, target_index)) if total_questions else 1
                return redirect(_ap_part_url(attempt, "frq", target_index))
            if action == "finish":
                _submit_ap_attempt(attempt)
                return redirect("apclasses:event_result", token=attempt.token)
            return redirect(_ap_part_url(attempt, "frq", current_index))

        if current_question:
            selected_answer = (request.POST.get(f"question_{current_question.id}") or "").strip().upper()
            if selected_answer not in {"A", "B", "C", "D", "E"}:
                selected_answer = ""
            APExamAnswer.objects.update_or_create(
                attempt=attempt,
                question=current_question,
                defaults={"selected_answer": selected_answer},
            )
            attempt.last_activity_at = timezone.now()
            attempt.save(update_fields=["last_activity_at"])
            _recalculate_attempt(attempt)

        action = request.POST.get("action")
        if action == "back":
            if current_index > 1:
                return redirect(_ap_part_url(attempt, requested_part, current_index - 1))
            if requested_part == APMultipleChoiceQuestion.PART_B:
                part_a_total = exam.questions.filter(part=APMultipleChoiceQuestion.PART_A).count()
                if part_a_total:
                    return redirect(_ap_part_url(attempt, APMultipleChoiceQuestion.PART_A, max(1, part_a_total)))
            return redirect(_ap_part_url(attempt, requested_part, current_index))
        if action == "next":
            if current_index < total_questions:
                return redirect(_ap_part_url(attempt, requested_part, current_index + 1))
            next_part = _next_ap_part_after(exam, requested_part)
            if next_part:
                return redirect(_ap_part_url(attempt, next_part, 1))
            _submit_ap_attempt(attempt)
            return redirect("apclasses:event_result", token=attempt.token)
        if action == "goto":
            try:
                target_index = int(request.POST.get("target_q") or current_index)
            except ValueError:
                target_index = current_index
            target_index = max(1, min(total_questions, target_index)) if total_questions else 1
            return redirect(_ap_part_url(attempt, requested_part, target_index))
        if action == "finish":
            next_part = _next_ap_part_after(exam, requested_part)
            if next_part:
                return redirect(_ap_part_url(attempt, next_part, 1))
            _submit_ap_attempt(attempt)
            return redirect("apclasses:event_result", token=attempt.token)

        return redirect(_ap_part_url(attempt, requested_part, current_index))

    selected_answer = ""
    if current_question:
        saved = APExamAnswer.objects.filter(attempt=attempt, question=current_question).first()
        if saved and saved.selected_answer:
            selected_answer = saved.selected_answer

    current_part = "FRQ" if requested_part == "frq" else ("Part A" if requested_part == APMultipleChoiceQuestion.PART_A else "Part B")
    section_title = current_part
    duration_minutes = _duration_for_ap_part(attempt.event, exam, requested_part)
    part_started_at = _get_or_start_ap_part_timer(request, attempt, requested_part)
    elapsed_seconds = int((timezone.now() - part_started_at).total_seconds())
    remaining_seconds = max(0, int(duration_minutes) * 60 - elapsed_seconds)

    if remaining_seconds <= 0 and total_questions:
        next_part = _next_ap_part_after(exam, requested_part)
        if next_part:
            return redirect(_ap_part_url(attempt, next_part, 1))
        _submit_ap_attempt(attempt)
        return redirect("apclasses:event_result", token=attempt.token)

    answered_ids = set()
    if requested_part != "frq":
        answered_ids = set(
            attempt.answers.filter(question__part=requested_part)
            .exclude(selected_answer="")
            .values_list("question_id", flat=True)
        )
        question_index_items = [
            {"number": idx, "id": question.id, "answered": question.id in answered_ids}
            for idx, question in enumerate(ordered_questions, start=1)
        ]
    else:
        question_index_items = [
            {"number": idx, "id": f"frq-{page.id}", "answered": False}
            for idx, page in enumerate(frq_pages, start=1)
        ]

    submissions = attempt.frq_submissions.order_by("page_number")

    return render(request, "apclasses/attempt.html", {
        "attempt": attempt,
        "event": attempt.event,
        "exam": exam,
        "current_question": current_question,
        "current_frq_page": current_frq_page,
        "current_item_id": (current_question.id if current_question else (f"frq-{current_frq_page.id}" if current_frq_page else "none")),
        "selected_answer": selected_answer,
        "current_index": current_index,
        "total_questions": total_questions,
        "question_numbers": range(1, total_questions + 1),
        "question_index_items": question_index_items,
        "is_first_question": (current_index <= 1 and requested_part == APMultipleChoiceQuestion.PART_A),
        "is_last_question": current_index >= total_questions if total_questions else True,
        "current_part": current_part,
        "current_part_key": requested_part,
        "section_title": section_title,
        "remaining_seconds": remaining_seconds,
        "frq_pages": frq_pages,
        "submissions": submissions,
    })


@require_POST
def upload_frq_submission_view(request, token):
    attempt = get_object_or_404(APExamAttempt, token=token)
    if not _attempt_belongs_to_request(request, attempt):
        raise Http404("Attempt not found")
    if attempt.status != "in_progress":
        messages.error(request, "This attempt has already been submitted.")
        return redirect("apclasses:event_result", token=attempt.token)

    page_number = request.POST.get("page_number") or 1
    try:
        page_number = int(page_number)
    except ValueError:
        page_number = 1

    image = request.FILES.get("image")
    file = request.FILES.get("file")
    if not image and not file:
        messages.error(request, "Upload an image or file for the FRQ answer.")
        return redirect("apclasses:attempt", token=attempt.token)

    submission, _created = APFRQSubmission.objects.update_or_create(
        attempt=attempt,
        page_number=page_number,
        defaults={"image": image, "file": file},
    )
    attempt.last_activity_at = timezone.now()
    attempt.save(update_fields=["last_activity_at"])
    messages.success(request, "FRQ handwritten answer uploaded.")
    return redirect("apclasses:attempt", token=attempt.token)



@require_POST
def submit_ap_attempt_view(request, token):
    attempt = get_object_or_404(APExamAttempt, token=token)
    if not _attempt_belongs_to_request(request, attempt):
        raise Http404("Attempt not found")
    _submit_ap_attempt(attempt)
    messages.success(request, "AP mock exam submitted.")
    return redirect("apclasses:event_result", token=attempt.token)



def ap_event_result_view(request, token):
    attempt = get_object_or_404(APExamAttempt.objects.select_related("event", "event__exam", "student"), token=token)
    if not _attempt_belongs_to_request(request, attempt):
        raise Http404("Attempt not found")
    if attempt.status != "submitted":
        return redirect("apclasses:attempt", token=attempt.token)

    exam = attempt.event.exam
    answers = {
        answer.question_id: answer
        for answer in attempt.answers.select_related("question").all()
    }

    questions = list(exam.questions.all().order_by("part", "number", "id"))
    part_a_questions = []
    part_b_questions = []
    for q in questions:
        if getattr(q, "part", "") == APMultipleChoiceQuestion.PART_B:
            part_b_questions.append(q)
        else:
            part_a_questions.append(q)

    def serialize_module(question_list):
        result = []
        correct_count = 0
        answered_count = 0
        for q in question_list:
            answer = answers.get(q.id)
            selected = answer.selected_answer if answer and answer.selected_answer else ""
            is_correct = bool(answer and answer.is_correct)
            if selected:
                answered_count += 1
            if is_correct:
                correct_count += 1
            status = "neutral"
            if selected:
                status = "correct" if is_correct else "incorrect"
            result.append({
                "id": q.id,
                "number": q.number,
                "status": status,
                "selected_answer": selected or "—",
                "correct_answer": getattr(q, "correct_answer", "") or "—",
            })
        total = len(question_list)
        percent = round((correct_count / total) * 100) if total else 0
        return {
            "questions": result,
            "correct": correct_count,
            "answered": answered_count,
            "total": total,
            "percent": percent,
        }

    display_name = _current_display_name(request, attempt)
    can_view_score = (
        attempt.event.show_score_immediately
        or _is_staff_user(request.user)
        or (request.user.is_authenticated and attempt.event.classrooms.filter(teacher=request.user, is_active=True).exists())
    )

    return render(request, "apclasses/result.html", {
        "attempt": attempt,
        "event": attempt.event,
        "exam": exam,
        "display_name": display_name,
        "total_score_value": int(round(float(attempt.score or 0))),
        "can_view_score": can_view_score,
        "part_a": serialize_module(part_a_questions),
        "part_b": serialize_module(part_b_questions),
    })


def ap_question_review_view(request, token, question_id):
    attempt = get_object_or_404(APExamAttempt.objects.select_related("event", "event__exam", "student"), token=token)
    if not _attempt_belongs_to_request(request, attempt):
        raise Http404("Attempt not found")
    if attempt.status != "submitted":
        return redirect("apclasses:attempt", token=attempt.token)
    exam = attempt.event.exam
    ordered_questions = list(exam.questions.all().order_by("part", "number", "id"))
    question = next((q for q in ordered_questions if q.id == question_id), None)
    if question is None:
        raise Http404("Question not found")

    position = next((idx for idx, q in enumerate(ordered_questions) if q.id == question.id), 0)
    previous_question = ordered_questions[position - 1] if position > 0 else None
    next_question = ordered_questions[position + 1] if position < len(ordered_questions) - 1 else None

    answer = APExamAnswer.objects.filter(attempt=attempt, question=question).first()
    selected_answer = answer.selected_answer if answer and answer.selected_answer else ""
    correct_answer = question.correct_answer or ""

    choices = []
    for letter in ["A", "B", "C", "D", "E"]:
        text_value = getattr(question, letter.lower(), "")
        image_value = getattr(question, f"image_{letter.lower()}", None)
        if not text_value and not image_value:
            continue

        state = ""
        if correct_answer and letter == correct_answer:
            state = "correct"
            if selected_answer == letter:
                state = "selected-correct"
        elif selected_answer and letter == selected_answer:
            state = "selected-incorrect"

        choices.append({
            "letter": letter,
            "text": text_value,
            "image": image_value,
            "state": state,
        })

    return render(request, "apclasses/review.html", {
        "attempt": attempt,
        "event": attempt.event,
        "exam": exam,
        "review_question": question,
        "selected_answer": selected_answer or "—",
        "correct_answer": correct_answer or "—",
        "choices": choices,
        "previous_question": previous_question,
        "next_question": next_question,
    })


def coming_soon_view(request):
    return render(request, "apclasses/coming_soon.html", {})


def _recalculate_attempt(attempt):
    answers = attempt.answers.select_related("question")
    total = attempt.event.exam.questions.count()
    answered = answers.exclude(selected_answer="").count()
    raw = sum(1 for answer in answers if answer.is_correct)
    score = Decimal("0.00")
    if total:
        score = (Decimal(raw) / Decimal(total)) * Decimal("100.00")
    attempt.total_questions = total
    attempt.answered_questions = answered
    attempt.raw_score = raw
    attempt.score = score.quantize(Decimal("0.01"))
    attempt.save(update_fields=["total_questions", "answered_questions", "raw_score", "score"])
