from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.db.models import Q
from datetime import timedelta
from django.contrib import messages
from django.http import JsonResponse

from .models import *


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


def finalize_attempt(attempt):
    if attempt.status == "submitted":
        return attempt

    attempt.status = "submitted"
    attempt.submitted_at = timezone.now()
    attempt.save(update_fields=["status", "submitted_at"])
    return attempt


def auto_submit_attempt(attempt):
    if attempt.status != "submitted":
        finalize_attempt(attempt)


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
            return redirect("global_event_attempt", guest_token=existing_attempt.guest_token)

        messages.error(request, "Another attempt is not allowed.")
        return redirect("global_event_detail", slug=slug)

    attempt = GlobalEventAttempt.objects.create(
        event=event,
        guest=guest,
        expires_at=min(
            now + timedelta(minutes=event.duration_minutes),
            event.end_at
        ),
        total_questions = (
            English_Question.objects.filter(test=event.test).count()
            + Math_Question.objects.filter(test=event.test).count()
        ),
    )

    return redirect("global_event_attempt", guest_token=attempt.guest_token)


@guest_required
def global_event_attempt_view(request, guest_token):
    attempt = get_object_or_404(
        GlobalEventAttempt.objects.select_related("event", "guest"),
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

    return render(request, "sat/guest/attempt.html", {
        "attempt": attempt,
        "event": attempt.event,
        "questions": [],
        "existing_answers": {},
        "time_left_seconds": attempt.time_left_seconds if hasattr(attempt, "time_left_seconds") else 0,
    })


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

    question_id = request.POST.get("question_id")
    section = request.POST.get("section")
    module = request.POST.get("module", "")
    answer = request.POST.get("answer")

    if not question_id or section not in ["english", "math"]:
        return JsonResponse({"ok": False, "error": "Invalid payload"}, status=400)

    GlobalEventAnswer.objects.update_or_create(
        attempt=attempt,
        section=section,
        module=module,
        question_id=int(question_id),
        defaults={"selected_answer": answer}
    )

    attempt.answered_questions = attempt.answers.exclude(selected_answer__isnull=True).exclude(selected_answer="").count()
    attempt.save(update_fields=["answered_questions"])

    return JsonResponse({"ok": True})


@guest_required
def submit_global_event_view(request, guest_token):
    if request.method != "POST":
        return redirect("global_event_attempt", guest_token=guest_token)

    attempt = get_object_or_404(GlobalEventAttempt, guest_token=guest_token)
    guest = get_guest_from_session(request)

    if not guest or attempt.guest_id != guest.id:
        return redirect("global_event_list")

    if attempt.status != "submitted":
        finalize_attempt(attempt)

    return redirect("global_event_result", guest_token=attempt.guest_token)


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

    return render(request, "sat/guest/result.html", {
        "attempt": attempt,
        "event": attempt.event,
        "show_score": attempt.event.show_score_immediately,
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