import json
from datetime import timedelta

from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.db.models import Q
from django.contrib import messages
from django.http import JsonResponse
from django.urls import reverse

from .models import (
    GlobalEvent,
    GuestParticipant,
    GlobalEventAttempt,
    GlobalEventAnswer,
    English_Question,
    Math_Question,
)

# Используем существующую проверку written math из обычного SAT flow
from .views import check_written


# =========================
# Helpers
# =========================

def get_client_ip(request):
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        return x_forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def get_guest_from_session(request):
    guest_id = request.session.get("guest_id")
    if not guest_id:
        return None
    try:
        return GuestParticipant.objects.get(guest_id=guest_id)
    except GuestParticipant.DoesNotExist:
        return None


def is_guest_mode(request):
    return bool(request.session.get("guest_mode") and request.session.get("guest_id"))


def guest_required(view_func):
    def _wrapped_view(request, *args, **kwargs):
        if not is_guest_mode(request):
            return redirect("guest_entry")
        return view_func(request, *args, **kwargs)
    return _wrapped_view


def normalize_module_name(module):
    if module in ["module_1", "m1"]:
        return "m1"
    if module in ["module_2", "m2"]:
        return "m2"
    return module


def module_query_name(module):
    module = normalize_module_name(module)
    if module == "m1":
        return "module_1"
    if module == "m2":
        return "module_2"
    return module


def normalize_answer(value):
    if value is None:
        return ""
    return str(value).strip().upper()


def next_module_redirect_url(attempt, section, module):
    module = normalize_module_name(module)

    order = [
        ("english", "m1"),
        ("english", "m2"),
        ("math", "m1"),
        ("math", "m2"),
    ]

    try:
        index = order.index((section, module))
    except ValueError:
        return None

    if index == len(order) - 1:
        return reverse("global_event_result", kwargs={"guest_token": attempt.guest_token})

    next_section, next_module = order[index + 1]
    module_param = "module_1" if next_module == "m1" else "module_2"

    base = reverse("global_event_attempt", kwargs={"guest_token": attempt.guest_token})
    return f"{base}?section={next_section}&module={module_param}"


def has_all_required_modules(attempt):
    modules = set(
        attempt.answers.values_list("section", "module").distinct()
    )
    required = {
        ("english", "m1"),
        ("english", "m2"),
        ("math", "m1"),
        ("math", "m2"),
    }
    return required.issubset(modules)


# =========================
# Custom raw -> SAT equivalent converter
# (per section)
# =========================

RAW_TO_EQUIV = [
    ((0, 1), 200),
    ((2, 2), 220),
    ((3, 3), 240),
    ((4, 4), 260),
    ((5, 5), 280),
    ((6, 6), 300),
    ((7, 7), 320),
    ((8, 8), 340),
    ((9, 9), 360),
    ((10, 10), 380),
    ((11, 11), 400),
    ((12, 12), 420),
    ((13, 13), 440),
    ((14, 14), 450),
    ((15, 15), 460),
    ((16, 16), 470),
    ((17, 17), 490),
    ((18, 18), 500),
    ((19, 19), 520),
    ((20, 20), 540),
    ((21, 21), 550),
    ((22, 22), 560),
    ((23, 23), 570),
    ((24, 24), 580),
    ((25, 25), 600),
]


def convert_raw_to_equiv(raw_score):
    try:
        raw_score = int(raw_score)
    except (TypeError, ValueError):
        raw_score = 0

    if raw_score < 0:
        raw_score = 0

    for (low, high), sat_equiv in RAW_TO_EQUIV:
        if low <= raw_score <= high:
            return sat_equiv

    # если выше диапазона
    return 600


# =========================
# Scoring
# =========================

def calculate_attempt_breakdown(attempt):
    ebrw_raw = 0
    math_raw = 0

    answers = attempt.answers.all()

    for ans in answers:
        is_correct = False

        if ans.section == "english":
            question = English_Question.objects.filter(id=ans.question_id).first()
            if question:
                is_correct = normalize_answer(ans.selected_answer) == normalize_answer(question.answer)
                if is_correct:
                    ebrw_raw += 1

        elif ans.section == "math":
            question = Math_Question.objects.filter(id=ans.question_id).first()
            if question:
                is_correct = (
                    ans.selected_answer is not None and
                    check_written(str(ans.selected_answer), question.answer)
                )
                if is_correct:
                    math_raw += 1

        if ans.is_correct != is_correct:
            ans.is_correct = is_correct
            ans.save(update_fields=["is_correct"])

    ebrw_score = convert_raw_to_equiv(ebrw_raw)
    math_score = convert_raw_to_equiv(math_raw)
    total_score = ebrw_score + math_score

    return {
        "ebrw_raw": ebrw_raw,
        "math_raw": math_raw,
        "ebrw_score": ebrw_score,
        "math_score": math_score,
        "total_score": total_score,
    }


def finalize_attempt(attempt):
    if attempt.status == "submitted":
        return attempt

    breakdown = calculate_attempt_breakdown(attempt)

    attempt.raw_score = breakdown["ebrw_raw"] + breakdown["math_raw"]
    attempt.score = breakdown["total_score"]   # leaderboard uses this total score
    attempt.status = "submitted"
    attempt.submitted_at = timezone.now()
    attempt.answered_questions = (
        attempt.answers.exclude(selected_answer__isnull=True)
        .exclude(selected_answer="")
        .count()
    )
    attempt.save(
        update_fields=["raw_score", "score", "status", "submitted_at", "answered_questions"]
    )

    return attempt


def auto_submit_attempt(attempt):
    if attempt.status != "submitted":
        finalize_attempt(attempt)


# =========================
# Views
# =========================

def guest_entry_view(request):
    if request.method == "POST":
        full_name = request.POST.get("full_name", "").strip()
        display_name = request.POST.get("display_name", "").strip()

        if not full_name:
            return render(request, "sat/guest/entry.html", {
                "error": "Full name or nickname is required."
            })

        if not request.session.session_key:
            request.session.create()

        guest = GuestParticipant.objects.create(
            full_name=full_name,
            display_name=display_name,
            session_key=request.session.session_key or "",
            first_ip=get_client_ip(request),
            user_agent=request.META.get("HTTP_USER_AGENT", "")
        )

        request.session["guest_mode"] = True
        request.session["guest_id"] = str(guest.guest_id)
        request.session["guest_name"] = guest.display_name or guest.full_name

        return redirect("global_event_list")

    return render(request, "sat/guest/entry.html")


def guest_logout_view(request):
    request.session.pop("guest_mode", None)
    request.session.pop("guest_id", None)
    request.session.pop("guest_name", None)
    return redirect("guest_entry")


@guest_required
def global_event_list_view(request):
    now = timezone.now()

    events = GlobalEvent.objects.filter(
        is_public=True
    ).filter(
        Q(status="live") | Q(status="scheduled")
    ).order_by("start_at")

    return render(request, "sat/guest/event_list.html", {
        "events": events,
        "now": now,
    })


@guest_required
def global_event_detail_view(request, slug):
    event = get_object_or_404(GlobalEvent, slug=slug, is_public=True)

    guest = get_guest_from_session(request)
    existing_attempt = None
    if guest:
        existing_attempt = GlobalEventAttempt.objects.filter(
            event=event,
            guest=guest
        ).first()

    return render(request, "sat/guest/event_detail.html", {
        "event": event,
        "existing_attempt": existing_attempt,
    })


@guest_required
def start_global_event_view(request, slug):
    if request.method != "POST":
        return redirect("global_event_detail", slug=slug)

    event = get_object_or_404(GlobalEvent, slug=slug, is_public=True)
    guest = get_guest_from_session(request)

    if not guest:
        return redirect("guest_entry")

    now = timezone.now()

    if not event.is_live_now:
        messages.error(request, "This event is not available right now.")
        return redirect("global_event_detail", slug=slug)

    submitted_code = request.POST.get("access_code", "").strip()
    if event.access_code and submitted_code != event.access_code:
        messages.error(request, "Invalid access code.")
        return redirect("global_event_detail", slug=slug)

    existing_attempt = GlobalEventAttempt.objects.filter(
        event=event,
        guest=guest
    ).first()

    if existing_attempt:
        if existing_attempt.status == "submitted":
            return redirect("global_event_result", guest_token=existing_attempt.guest_token)

        if existing_attempt.status == "in_progress" and event.allow_resume:
            return redirect(
                f"{reverse('global_event_attempt', kwargs={'guest_token': existing_attempt.guest_token})}"
                f"?section=english&module=module_1"
            )

        messages.error(request, "Another attempt is not allowed.")
        return redirect("global_event_detail", slug=slug)

    total_questions = (
        English_Question.objects.filter(test=event.test).count() +
        Math_Question.objects.filter(test=event.test).count()
    )

    attempt = GlobalEventAttempt.objects.create(
        event=event,
        guest=guest,
        expires_at=min(
            now + timedelta(minutes=event.duration_minutes),
            event.end_at
        ),
        total_questions=total_questions,
    )

    return redirect(
        f"{reverse('global_event_attempt', kwargs={'guest_token': attempt.guest_token})}"
        f"?section=english&module=module_1"
    )


@guest_required
def global_event_attempt_view(request, guest_token):
    attempt = get_object_or_404(
        GlobalEventAttempt.objects.select_related("event", "guest", "event__test"),
        guest_token=guest_token
    )

    guest = get_guest_from_session(request)
    if not guest or attempt.guest_id != guest.id:
        return redirect("global_event_list")

    if attempt.status == "submitted":
        return redirect("global_event_result", guest_token=attempt.guest_token)

    if timezone.now() > attempt.expires_at:
        auto_submit_attempt(attempt)
        return redirect("global_event_result", guest_token=attempt.guest_token)

    test = attempt.event.test

    section = request.GET.get("section", "english")
    module = request.GET.get("module", "module_1")
    module_db = module_query_name(module)

    if section == "english":
        questions = English_Question.objects.filter(
            test=test,
            module=module_db
        ).order_by("number")

        return render(request, "sat/guest/attempt_eng.html", {
            "attempt": attempt,
            "event": attempt.event,
            "test": test,
            "questions": questions,
            "section": section,
            "module": module,
            "time_left_seconds": attempt.time_left_seconds,
            "custom_time_seconds": attempt.time_left_seconds,  # на случай старого шаблона
        })

    elif section == "math":
        questions = Math_Question.objects.filter(
            test=test,
            module=module_db
        ).order_by("number")

        questions_data = []
        for q in questions:
            questions_data.append({
                "id": q.id,
                "passage": q.passage or "",
                "number": q.number,
                "question": q.question or "",
                "a": q.get_a() if hasattr(q, "get_a") else "",
                "b": q.get_b() if hasattr(q, "get_b") else "",
                "c": q.get_c() if hasattr(q, "get_c") else "",
                "d": q.get_d() if hasattr(q, "get_d") else "",
                "type": str(q.written),
                "graph": q.get_graph() if hasattr(q, "get_graph") else "",
            })

        return render(request, "sat/guest/attempt_math.html", {
            "attempt": attempt,
            "event": attempt.event,
            "test": test,
            "questions": questions,
            "questions_data": questions_data,
            "section": section,
            "module": module,
            "time_left_seconds": attempt.time_left_seconds,
            "custom_time_seconds": attempt.time_left_seconds,  # на случай старого шаблона
        })

    return redirect("global_event_detail", slug=attempt.event.slug)


@guest_required
def save_global_event_answer_view(request, guest_token):
    if request.method != "POST":
        return JsonResponse({"ok": False, "error": "Invalid method"}, status=405)

    attempt = get_object_or_404(GlobalEventAttempt, guest_token=guest_token)
    guest = get_guest_from_session(request)

    if not guest or attempt.guest_id != guest.id:
        return JsonResponse({"ok": False, "error": "Forbidden"}, status=403)

    if attempt.status != "in_progress":
        return JsonResponse({"ok": False, "error": "Attempt already closed"}, status=400)

    if timezone.now() > attempt.expires_at:
        auto_submit_attempt(attempt)
        return JsonResponse({"ok": False, "error": "Time is over"}, status=400)

    # Поддержка batch JSON из шаблонов
    if request.content_type and "application/json" in request.content_type:
        try:
            payload = json.loads(request.body.decode("utf-8")) if request.body else {}
        except Exception:
            return JsonResponse({"ok": False, "error": "Invalid JSON"}, status=400)

        answers = payload.get("answers", [])
        section = payload.get("section")
        module = normalize_module_name(payload.get("module", ""))

        if section not in ["english", "math"]:
            return JsonResponse({"ok": False, "error": "Invalid section"}, status=400)

        for item in answers:
            question_id = item.get("questionID")
            answer = item.get("answer")
            time_spent = item.get("time_spent", 0)

            if not question_id:
                continue

            GlobalEventAnswer.objects.update_or_create(
                attempt=attempt,
                section=section,
                module=module,
                question_id=int(question_id),
                defaults={
                    "selected_answer": answer,
                    "time_spent": int(time_spent or 0),
                }
            )
    else:
        # fallback на одиночный POST
        question_id = request.POST.get("question_id")
        section = request.POST.get("section")
        module = normalize_module_name(request.POST.get("module", ""))
        answer = request.POST.get("answer", "")
        time_spent = request.POST.get("time_spent", 0)

        if not question_id or section not in ["english", "math"]:
            return JsonResponse({"ok": False, "error": "Invalid payload"}, status=400)

        GlobalEventAnswer.objects.update_or_create(
            attempt=attempt,
            section=section,
            module=module,
            question_id=int(question_id),
            defaults={
                "selected_answer": answer,
                "time_spent": int(time_spent or 0),
            }
        )

    attempt.answered_questions = (
        attempt.answers.exclude(selected_answer__isnull=True)
        .exclude(selected_answer="")
        .count()
    )
    attempt.save(update_fields=["answered_questions"])

    return JsonResponse({"ok": True})


@guest_required
def submit_global_event_view(request, guest_token):
    if request.method != "POST":
        return JsonResponse({"ok": False, "error": "Invalid method"}, status=405)

    attempt = get_object_or_404(GlobalEventAttempt, guest_token=guest_token)
    guest = get_guest_from_session(request)

    if not guest or attempt.guest_id != guest.id:
        return JsonResponse({"ok": False, "error": "Forbidden"}, status=403)

    try:
        payload = json.loads(request.body.decode("utf-8")) if request.body else {}
    except Exception:
        payload = {}

    section = payload.get("section")
    module = normalize_module_name(payload.get("module"))

    if section not in ["english", "math"] or module not in ["m1", "m2"]:
        return JsonResponse(
            {"ok": False, "error": f"Invalid section/module: {section} / {module}"},
            status=400
        )

    # Только после math m2 закрываем весь тест и считаем total
    if section == "math" and module == "m2":
        finalize_attempt(attempt)
        return JsonResponse({
            "ok": True,
            "redirect_url": reverse("global_event_result", kwargs={"guest_token": attempt.guest_token})
        })

    redirect_url = next_module_redirect_url(attempt, section, module)
    if not redirect_url:
        return JsonResponse({"ok": False, "error": "Could not determine next step"}, status=400)

    return JsonResponse({
        "ok": True,
        "redirect_url": redirect_url
    })


@guest_required
def global_event_result_view(request, guest_token):
    attempt = get_object_or_404(
        GlobalEventAttempt.objects.select_related("event", "guest"),
        guest_token=guest_token
    )

    guest = get_guest_from_session(request)
    if not guest or attempt.guest_id != guest.id:
        return redirect("global_event_list")

    if attempt.status != "submitted":
        finalize_attempt(attempt)

    breakdown = calculate_attempt_breakdown(attempt)

    return render(request, "sat/guest/result.html", {
        "attempt": attempt,
        "event": attempt.event,
        "show_score": attempt.event.show_score_immediately,

        "total_score": breakdown["total_score"],
        "ebrw_score": breakdown["ebrw_score"],
        "math_score": breakdown["math_score"],

        # если захочешь где-то показать raw
        "ebrw_raw": breakdown["ebrw_raw"],
        "math_raw": breakdown["math_raw"],
    })


@guest_required
def global_event_leaderboard_view(request, slug):
    event = get_object_or_404(GlobalEvent, slug=slug, is_public=True)

    if not event.show_leaderboard:
        return redirect("global_event_detail", slug=slug)

    attempts = (
        event.attempts
        .filter(status="submitted")
        .select_related("guest")
        .order_by("-score", "submitted_at")[:100]
    )

    return render(request, "sat/guest/leaderboard.html", {
        "event": event,
        "attempts": attempts,
    })
