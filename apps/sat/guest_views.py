import json
from datetime import timedelta
from functools import wraps
from itertools import chain

from django.contrib import messages
from django.db import models, transaction
from django.db.models import Q
from django.http import JsonResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from .models import (
    English_Question,
    GlobalEvent,
    GlobalEventAnswer,
    GlobalEventAttempt,
    GlobalEventModuleDraft,
    GuestParticipant,
    Math_Question,
)
from .views import (
    _canonical_partial_module_answers,
    _normalize_live_test_answer,
    _normalize_review_choice_letter,
    _review_choices_payload,
    _review_question_payload,
    _validate_regular_module_answers,
    check_written,
    get_test_mode,
    get_test_sequence,
)
from .libs import calculator
from .text_formatting import format_english_questions_for_display
from .answer_matching import check_english_answer

try:
    from apps.apclasses.models import APExamEvent
except Exception:  # pragma: no cover
    APExamEvent = None


# =========================
# Helpers
# =========================

VALID_SECTIONS = {"english", "math"}
VALID_MODULES = {"m1", "m2"}
GUEST_SUBMIT_GRACE_SECONDS = 300


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
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not is_guest_mode(request) or get_guest_from_session(request) is None:
            return redirect("guest_entry")
        return view_func(request, *args, **kwargs)
    return _wrapped_view


def normalize_module_name(module):
    value = str(module or "").strip().lower()
    if value in {"module_1", "module-1", "module 1", "1", "m1"}:
        return "m1"
    if value in {"module_2", "module-2", "module 2", "2", "m2"}:
        return "m2"
    return value


def module_query_name(module):
    module = normalize_module_name(module)
    return "module_1" if module == "m1" else "module_2" if module == "m2" else module


def normalize_answer(value):
    if value is None:
        return ""
    return str(value).strip().upper()


def _question_model(section):
    if section == "english":
        return English_Question
    if section == "math":
        return Math_Question
    return None


def _questions_for_step(test, section, module, *, formatted=False):
    model = _question_model(section)
    if model is None:
        return []
    questions = list(model.objects.filter(
        test=test,
        module=module_query_name(module),
    ).order_by("number", "id"))
    if formatted and section == "english":
        questions = list(format_english_questions_for_display(questions))
    return questions


def next_module_redirect_url(attempt, section, module):
    module = normalize_module_name(module)
    sequence = get_test_sequence(attempt.event.test)
    try:
        index = sequence.index((section, module))
    except ValueError:
        return None
    if index == len(sequence) - 1:
        return reverse("global_event_result", kwargs={"guest_token": attempt.guest_token})
    next_section, next_module = sequence[index + 1]
    base = reverse("global_event_attempt", kwargs={"guest_token": attempt.guest_token})
    return f"{base}?section={next_section}&module={module_query_name(next_module)}"


def _completed_guest_module_pairs(attempt):
    completed = set()
    for item in (attempt.completed_modules or []):
        if isinstance(item, str) and ":" in item:
            section, module = item.split(":", 1)
        elif isinstance(item, (list, tuple)) and len(item) == 2:
            section, module = item
        elif isinstance(item, dict):
            section, module = item.get("section"), item.get("module")
        else:
            continue
        section = str(section or "").strip().lower()
        module = normalize_module_name(module)
        if section in VALID_SECTIONS and module in VALID_MODULES:
            completed.add((section, module))
    return completed


def _ordered_completed_modules(attempt, completed):
    sequence = get_test_sequence(attempt.event.test)
    return [f"{section}:{module}" for section, module in sequence if (section, module) in completed]


def has_all_required_modules(attempt):
    required = set(get_test_sequence(attempt.event.test))
    return bool(required) and required.issubset(_completed_guest_module_pairs(attempt))


def get_guest_current_step(attempt):
    sequence = get_test_sequence(attempt.event.test)
    if not sequence:
        return None
    completed = _completed_guest_module_pairs(attempt)
    for step in sequence:
        if step not in completed:
            return step
    return None


def _event_availability(event, now=None):
    now = now or timezone.now()
    if not event.is_public or event.status in {"draft", "closed"}:
        return {"state": "unavailable", "label": "Unavailable", "can_start": False}
    if event.always_live:
        if event.status == "live":
            return {"state": "live", "label": "Live now", "can_start": True}
        return {"state": "upcoming", "label": "Scheduled", "can_start": False}
    if now > event.end_at:
        return {"state": "ended", "label": "Ended", "can_start": False}
    if now < event.start_at:
        return {"state": "upcoming", "label": "Upcoming", "can_start": False}
    if event.status == "live":
        return {"state": "live", "label": "Live now", "can_start": True}
    return {"state": "waiting", "label": "Waiting to open", "can_start": False}


def _event_hard_ended(event, now=None):
    """Return whether an in-progress attempt must stop immediately.

    An admin making an event private or moving it out of the Live state must
    close existing guest attempts too.  Previously only the calendar end or
    explicit Closed state was checked, so a hidden/draft event could keep
    running through a bookmarked attempt URL.
    """
    now = now or timezone.now()
    if not event.is_public or event.status != "live":
        return True
    return not event.always_live and now >= event.end_at


def _guest_attempt_expiry(event, sequence, now=None):
    now = now or timezone.now()
    if not event.always_live:
        return event.end_at
    total_seconds = sum(max(int(event.get_module_duration(section) or 0), 1) * 60 for section, _ in sequence)
    if event.allow_resume:
        return now + timedelta(days=7)
    return now + timedelta(seconds=max(total_seconds + 1800, 3600))


def _repair_guest_attempt_expiry(attempt):
    """Keep an active attempt aligned with event scheduling changes.

    Always-live events need a rolling resume window.  Scheduled events should
    follow an administrator extending or shortening ``end_at`` instead of
    retaining a stale deadline captured when the attempt was created.
    """
    if attempt.status != "in_progress":
        return
    now = timezone.now()
    if attempt.event.always_live:
        if attempt.expires_at <= now:
            attempt.expires_at = _guest_attempt_expiry(
                attempt.event,
                get_test_sequence(attempt.event.test),
                now,
            )
            attempt.save(update_fields=["expires_at"])
        return
    if attempt.expires_at != attempt.event.end_at:
        attempt.expires_at = attempt.event.end_at
        attempt.save(update_fields=["expires_at"])


def _finalize_guest_attempt_safely(attempt_id):
    """Finalize once while serializing against autosave/module submission."""
    with transaction.atomic():
        locked = (
            GlobalEventAttempt.objects.select_for_update()
            .select_related("event", "event__test", "guest")
            .get(pk=attempt_id)
        )
        _repair_guest_attempt_expiry(locked)
        _sync_all_guest_drafts(locked)
        finalize_attempt(locked)
        return locked


def _draft_remaining_seconds(draft):
    return max(int((draft.deadline_at - timezone.now()).total_seconds()), 0)


def _guest_submit_recovery_allowed(draft, payload, now=None):
    """Allow the browser's frozen deadline snapshot during a short grace window.

    At 0:00 the UI is locked immediately and the final snapshot is stored in
    localStorage before the request is sent.  A slow connection may deliver that
    request just after ``deadline_at``.  The grace window prevents data loss while
    still refusing arbitrary late edits: the request must explicitly be the
    deadline snapshot and its declared deadline must match the server deadline.
    """
    now = now or timezone.now()
    if now > draft.deadline_at + timedelta(seconds=GUEST_SUBMIT_GRACE_SECONDS):
        return False
    if not bool(payload.get("deadline_reached")):
        return False
    try:
        client_deadline = int(payload.get("client_deadline_at") or 0)
    except (TypeError, ValueError):
        return False
    server_deadline = int(draft.deadline_at.timestamp() * 1000)
    return abs(client_deadline - server_deadline) <= 5000


def _seed_guest_draft_answers(attempt, section, module, questions):
    saved = {
        answer.question_id: answer
        for answer in attempt.answers.filter(section=section, module=module)
    }
    result = []
    for question in questions:
        answer = saved.get(question.id)
        if answer:
            result.append({
                "questionID": question.id,
                "answer": answer.selected_answer,
                "time_spent": max(int(answer.time_spent or 0), 0),
            })
    return result


def _ensure_guest_module_draft(attempt, section, module, questions=None):
    section = str(section or "").strip().lower()
    module = normalize_module_name(module)
    questions = list(questions if questions is not None else _questions_for_step(attempt.event.test, section, module))
    now = timezone.now()
    duration_seconds = max(int(attempt.event.get_module_duration(section) or 0), 1) * 60
    deadline = min(now + timedelta(seconds=duration_seconds), attempt.expires_at)
    draft, created = GlobalEventModuleDraft.objects.get_or_create(
        attempt=attempt,
        section=section,
        module=module,
        defaults={
            "answers": _seed_guest_draft_answers(attempt, section, module, questions),
            "time_spent": [0 for _ in questions],
            "eliminated_choices": [[] for _ in questions],
            "marked_for_review": [False for _ in questions],
            "deadline_at": deadline,
        },
    )
    if created or attempt.current_module_started_at is None:
        attempt.current_module_started_at = draft.created_at or now
        attempt.save(update_fields=["current_module_started_at"])
    return draft


def _guest_draft_state_payload(draft, questions):
    question_ids = [question.id for question in questions]
    lookup = {
        int(item.get("questionID")): item
        for item in (draft.answers or [])
        if isinstance(item, dict) and str(item.get("questionID", "")).isdigit()
    }
    answers, time_spent = [], []
    for question_id in question_ids:
        item = lookup.get(question_id, {})
        answers.append(item.get("answer"))
        try:
            time_spent.append(max(int(item.get("time_spent", 0) or 0), 0))
        except (TypeError, ValueError):
            time_spent.append(0)

    def nested(value):
        rows = []
        if isinstance(value, list):
            for item in value[:len(question_ids)]:
                row = []
                if isinstance(item, list):
                    row = [str(choice).upper() for choice in item if str(choice).upper() in {"A", "B", "C", "D"}]
                rows.append(row)
        rows.extend([[] for _ in range(len(question_ids) - len(rows))])
        return rows

    def flags(value):
        result = [bool(item) for item in value[:len(question_ids)]] if isinstance(value, list) else []
        result.extend([False for _ in range(len(question_ids) - len(result))])
        return result

    return {
        "answers": answers,
        "timeSpent": time_spent,
        "eliminatedChoices": nested(draft.eliminated_choices),
        "markedForReview": flags(draft.marked_for_review),
        "currentQuestionIndex": min(max(int(draft.current_question_index or 0), 0), max(len(question_ids) - 1, 0)),
        "deadlineAt": int(draft.deadline_at.timestamp() * 1000),
        "updatedAt": int((draft.updated_at or draft.created_at or timezone.now()).timestamp() * 1000),
    }


def _merge_answer_items(existing, incoming):
    merged = {
        int(item["questionID"]): dict(item)
        for item in (existing or [])
        if isinstance(item, dict) and str(item.get("questionID", "")).isdigit()
    }
    for item in incoming:
        merged[int(item["questionID"])] = dict(item)
    return list(merged.values())


def _sync_guest_answer_rows(attempt, section, module, answers):
    """Persist one module in bulk.

    Autosave intentionally writes only ``GlobalEventModuleDraft``.  The durable
    answer rows are materialized once when a module is submitted (or when an
    attempt is force-finalized).  This avoids one ``UPDATE OR CREATE`` query per
    question on every autosave and keeps the attempt row lock short.
    """
    canonical = {}
    for item in answers or []:
        if not isinstance(item, dict) or not str(item.get("questionID", "")).isdigit():
            continue
        question_id = int(item["questionID"])
        try:
            spent = min(max(int(item.get("time_spent", 0) or 0), 0), 24 * 60 * 60)
        except (TypeError, ValueError):
            spent = 0
        canonical[question_id] = {
            "selected_answer": item.get("answer"),
            "time_spent": spent,
        }

    if canonical:
        existing = {
            row.question_id: row
            for row in GlobalEventAnswer.objects.filter(
                attempt=attempt,
                section=section,
                module=module,
                question_id__in=canonical.keys(),
            )
        }
        to_create, to_update = [], []
        for question_id, values in canonical.items():
            row = existing.get(question_id)
            if row is None:
                to_create.append(GlobalEventAnswer(
                    attempt=attempt,
                    section=section,
                    module=module,
                    question_id=question_id,
                    selected_answer=values["selected_answer"],
                    time_spent=values["time_spent"],
                ))
            else:
                row.selected_answer = values["selected_answer"]
                row.time_spent = values["time_spent"]
                to_update.append(row)
        if to_create:
            GlobalEventAnswer.objects.bulk_create(to_create, ignore_conflicts=True)
        if to_update:
            GlobalEventAnswer.objects.bulk_update(to_update, ["selected_answer", "time_spent"])

    attempt.answered_questions = (
        attempt.answers.exclude(selected_answer__isnull=True).exclude(selected_answer="").count()
    )
    attempt.save(update_fields=["answered_questions"])


def _persist_guest_draft_payload(attempt, draft, payload, *, require_complete=False):
    section, module = draft.section, draft.module
    raw_answers = payload.get("answers") or []
    validator = _validate_regular_module_answers if require_complete else _canonical_partial_module_answers
    is_valid, error, canonical = validator(attempt.event.test, section, module, raw_answers)
    if not is_valid:
        return False, error

    questions = _questions_for_step(attempt.event.test, section, module)
    expected_count = len(questions)
    draft.answers = canonical if require_complete else _merge_answer_items(draft.answers, canonical)
    draft.time_spent = [
        max(int(item.get("time_spent", 0) or 0), 0)
        for item in draft.answers
    ]

    eliminated = payload.get("eliminated_choices", payload.get("eliminatedChoices"))
    if isinstance(eliminated, list):
        rows = []
        for item in eliminated[:expected_count]:
            row = []
            if isinstance(item, list):
                row = [str(choice).upper() for choice in item if str(choice).upper() in {"A", "B", "C", "D"}]
            rows.append(row)
        rows.extend([[] for _ in range(expected_count - len(rows))])
        draft.eliminated_choices = rows

    marked = payload.get("marked_for_review", payload.get("markedForReview"))
    if isinstance(marked, list):
        flags = [bool(item) for item in marked[:expected_count]]
        flags.extend([False for _ in range(expected_count - len(flags))])
        draft.marked_for_review = flags

    try:
        current_index = int(payload.get("current_question_index", payload.get("currentQuestionIndex", draft.current_question_index)) or 0)
    except (TypeError, ValueError):
        current_index = 0
    draft.current_question_index = min(max(current_index, 0), max(expected_count - 1, 0))
    draft.save(update_fields=[
        "answers", "time_spent", "eliminated_choices", "marked_for_review",
        "current_question_index", "updated_at",
    ])
    return True, ""


def _ensure_guest_module_answer_rows(attempt, section, module):
    questions = _questions_for_step(attempt.event.test, section, module)
    existing_ids = set(attempt.answers.filter(section=section, module=module).values_list("question_id", flat=True))
    missing = [question.id for question in questions if question.id not in existing_ids]
    if missing:
        GlobalEventAnswer.objects.bulk_create([
            GlobalEventAnswer(
                attempt=attempt,
                section=section,
                module=module,
                question_id=question_id,
                selected_answer=None,
                time_spent=0,
            )
            for question_id in missing
        ], ignore_conflicts=True)


def _sync_all_guest_drafts(attempt):
    for draft in attempt.module_drafts.all():
        _sync_guest_answer_rows(attempt, draft.section, draft.module, draft.answers or [])


def _complete_guest_module_locked(attempt, section, module):
    section = str(section or "").strip().lower()
    module = normalize_module_name(module)
    completed = _completed_guest_module_pairs(attempt)
    if (section, module) not in completed:
        draft = GlobalEventModuleDraft.objects.filter(attempt=attempt, section=section, module=module).first()
        if draft:
            _sync_guest_answer_rows(attempt, section, module, draft.answers or [])
        _ensure_guest_module_answer_rows(attempt, section, module)
        completed.add((section, module))
        attempt.completed_modules = _ordered_completed_modules(attempt, completed)
        attempt.current_module_started_at = None
        attempt.save(update_fields=["completed_modules", "current_module_started_at"])
        GlobalEventModuleDraft.objects.filter(attempt=attempt, section=section, module=module).delete()

    current = get_guest_current_step(attempt)
    if current is None:
        finalize_attempt(attempt)
        return reverse("global_event_result", kwargs={"guest_token": attempt.guest_token})
    base = reverse("global_event_attempt", kwargs={"guest_token": attempt.guest_token})
    return f"{base}?section={current[0]}&module={module_query_name(current[1])}"


def _complete_guest_module(attempt, section, module):
    with transaction.atomic():
        locked = GlobalEventAttempt.objects.select_for_update().select_related("event", "event__test").get(pk=attempt.pk)
        return _complete_guest_module_locked(locked, section, module)


def _guest_access_failure_state(request, event):
    key = f"guest_event_access_failures_{event.pk}"
    state = request.session.get(key, {})
    now_ts = int(timezone.now().timestamp())
    blocked_until = int(state.get("blocked_until", 0) or 0)
    return key, state, now_ts, blocked_until


def _record_guest_access_failure(request, event):
    key, state, now_ts, _ = _guest_access_failure_state(request, event)
    window_started = int(state.get("window_started", now_ts) or now_ts)
    if now_ts - window_started > 900:
        state = {"window_started": now_ts, "count": 0}
    state["count"] = int(state.get("count", 0) or 0) + 1
    if state["count"] >= 10:
        state["blocked_until"] = now_ts + 900
    request.session[key] = state
    request.session.modified = True


def _clear_guest_access_failures(request, event):
    request.session.pop(f"guest_event_access_failures_{event.pk}", None)
    request.session.modified = True


# =========================
# Scoring
# =========================

# Level Check / short global-event scale.
# This is intentionally kept for 1-module Level Check events; forcing the
# full SAT calculator onto a single-module test gives misleading scores.
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

    return 600


def empty_correct_counts():
    return {
        "english": {"m1": 0, "m2": 0},
        "math": {"m1": 0, "m2": 0},
    }


def module_key(module):
    module = normalize_module_name(module)
    if module in ["m1", "m2"]:
        return module
    return "m1"


def empty_module_totals():
    return {
        "english": {"m1": 0, "m2": 0},
        "math": {"m1": 0, "m2": 0},
    }


def get_event_question_totals(test):
    totals = empty_module_totals()

    for module, count in (
        English_Question.objects.filter(test=test)
        .values_list("module")
        .annotate(count=models.Count("id"))
    ):
        key = module_key(module)
        if key in totals["english"]:
            totals["english"][key] += count

    for module, count in (
        Math_Question.objects.filter(test=test)
        .values_list("module")
        .annotate(count=models.Count("id"))
    ):
        key = module_key(module)
        if key in totals["math"]:
            totals["math"][key] += count

    return totals


def section_has_two_modules(totals, section):
    return totals[section]["m1"] > 0 and totals[section]["m2"] > 0


def get_event_scoring_type(test):
    """Return the Guest Mode SAT scoring strategy for *test*.

    A complete two-module section can use the same adaptive SAT-style calculator
    as regular practice tests.  Short/imported Guest tests often contain only
    one module (or a non-standard number of questions).  Those tests still need
    the normal SAT score range, so we estimate the missing module from the
    student's percentage on the available module instead of falling back to the
    old 200-600 Level Check scale.

    This distinction is important: ``sat_estimated`` is an SAT-style normalized
    estimate, not an official College Board equated score.
    """
    totals = get_event_question_totals(test)
    test_mode = get_test_mode(test)

    if test_mode == "full":
        if not (totals["english"]["m1"] or totals["english"]["m2"]):
            return "empty"
        if not (totals["math"]["m1"] or totals["math"]["m2"]):
            return "empty"
        return "sat_standard" if (
            section_has_two_modules(totals, "english")
            and section_has_two_modules(totals, "math")
        ) else "sat_estimated"

    if test_mode == "ebrw_only":
        if not (totals["english"]["m1"] or totals["english"]["m2"]):
            return "empty"
        return "sat_standard" if section_has_two_modules(totals, "english") else "sat_estimated"

    if test_mode == "math_only":
        if not (totals["math"]["m1"] or totals["math"]["m2"]):
            return "empty"
        return "sat_standard" if section_has_two_modules(totals, "math") else "sat_estimated"

    return "empty"


def is_standard_sat_question_count(test):
    totals = get_event_question_totals(test)
    test_mode = get_test_mode(test)

    english_standard = totals["english"] == {"m1": 27, "m2": 27}
    math_standard = totals["math"] == {"m1": 22, "m2": 22}

    if test_mode == "full":
        return english_standard and math_standard
    if test_mode == "ebrw_only":
        return english_standard
    if test_mode == "math_only":
        return math_standard
    return False


def get_event_scoring_label(test):
    scoring_type = get_event_scoring_type(test)
    test_mode = get_test_mode(test)

    if scoring_type == "sat_standard":
        normalized = "" if is_standard_sat_question_count(test) else " normalized"
        if test_mode == "full":
            return f"SAT-style{normalized} 400–1600"
        return f"SAT-style{normalized} 200–800"

    if scoring_type == "sat_estimated":
        if test_mode == "full":
            return "SAT-style normalized estimate 400–1600"
        return "SAT-style normalized estimate 200–800"

    return "Score unavailable"


def scale_correct_to_calculator_total(correct, actual_total, expected_total):
    if not actual_total:
        return 0
    return (correct / actual_total) * expected_total


def _normalize_section_counts_for_regular_calculator(section, correct_counts, totals):
    """Normalize one Guest section to the calculator's expected module sizes.

    If both modules exist, each module is normalized independently.  If only one
    module exists, its accuracy is projected to both calculator modules.  That
    keeps the section on the SAT 200-800 range without pretending that a missing
    module was answered incorrectly.
    """
    config = calculator.SECTION_CONFIG[section]
    actual_m1 = totals[section]["m1"]
    actual_m2 = totals[section]["m2"]
    expected_m1 = config["m1_total"]
    expected_m2 = config["m2_total"]

    if actual_m1 and actual_m2:
        return {
            "m1": scale_correct_to_calculator_total(
                correct_counts[section]["m1"], actual_m1, expected_m1
            ),
            "m2": scale_correct_to_calculator_total(
                correct_counts[section]["m2"], actual_m2, expected_m2
            ),
        }

    if actual_m1:
        ratio = max(0.0, min(correct_counts[section]["m1"] / actual_m1, 1.0))
        return {"m1": ratio * expected_m1, "m2": ratio * expected_m2}

    if actual_m2:
        ratio = max(0.0, min(correct_counts[section]["m2"] / actual_m2, 1.0))
        return {"m1": ratio * expected_m1, "m2": ratio * expected_m2}

    return {"m1": 0, "m2": 0}


def normalize_counts_for_regular_calculator(correct_counts, totals):
    return {
        "english": _normalize_section_counts_for_regular_calculator(
            "english", correct_counts, totals
        ),
        "math": _normalize_section_counts_for_regular_calculator(
            "math", correct_counts, totals
        ),
    }


def regular_score_from_counts(test_mode, correct_counts, totals):
    calculator_counts = normalize_counts_for_regular_calculator(correct_counts, totals)

    if test_mode == "full":
        return calculator.get_total(
            calculator_counts["english"]["m1"],
            calculator_counts["english"]["m2"],
            calculator_counts["math"]["m1"],
            calculator_counts["math"]["m2"],
        )

    if test_mode == "ebrw_only":
        english_score, english_range = calculator.get_english(
            calculator_counts["english"]["m1"],
            calculator_counts["english"]["m2"],
        )
        return {
            "total": english_score,
            "range_total": english_range,
            "sections": {
                "english": {"score": english_score, "range": english_range},
                "math": None,
            },
        }

    if test_mode == "math_only":
        math_score, math_range = calculator.get_math(
            calculator_counts["math"]["m1"],
            calculator_counts["math"]["m2"],
        )
        return {
            "total": math_score,
            "range_total": math_range,
            "sections": {
                "english": None,
                "math": {"score": math_score, "range": math_range},
            },
        }

    return {
        "total": 0,
        "range_total": {"lower": 0, "upper": 0},
        "sections": {"english": None, "math": None},
    }


def raw_to_25_equivalent(raw_score, total_questions):
    if not total_questions:
        return 0
    ratio = max(0, min(raw_score / total_questions, 1))
    return int((ratio * 25) + 0.5)


def level_check_score(raw_score, total_questions):
    return convert_raw_to_equiv(raw_to_25_equivalent(raw_score, total_questions))


def calculate_level_check_percentage(raw_score, total_questions):
    """Return a safe percentage for Level Check placement."""
    try:
        raw_score = int(raw_score or 0)
        total_questions = int(total_questions or 0)
    except (TypeError, ValueError):
        return 0

    if total_questions <= 0:
        return 0

    ratio = max(0, min(raw_score / total_questions, 1))
    return round(ratio * 100, 1)


def get_level_check_placement(raw_score, total_questions):
    """Map Level Check percentage to the student's allowed/recommended level."""
    percentage = calculate_level_check_percentage(raw_score, total_questions)

    if percentage >= 85:
        level_number = 5
        level_name = "Advanced"
    elif percentage >= 70:
        level_number = 4
        level_name = "Upper-Intermediate"
    elif percentage >= 55:
        level_number = 3
        level_name = "Intermediate"
    elif percentage >= 40:
        level_number = 2
        level_name = "Beginner"
    else:
        level_number = 1
        level_name = "Foundation"

    return {
        "percentage": percentage,
        "level_number": level_number,
        "level_name": level_name,
        "label": f"Level {level_number} — {level_name}",
    }


def mark_answers_and_count_correct(attempt):
    """Score all guest answers without one query per question.

    Only questions belonging to the event test are considered.  This also keeps
    legacy/corrupted answer rows from influencing a score.
    """
    ebrw_raw = 0
    math_raw = 0
    correct_counts = empty_correct_counts()
    answers = list(attempt.answers.all())

    english_ids = {answer.question_id for answer in answers if answer.section == "english"}
    math_ids = {answer.question_id for answer in answers if answer.section == "math"}
    english_map = English_Question.objects.filter(
        id__in=english_ids,
        test=attempt.event.test,
    ).in_bulk()
    math_map = Math_Question.objects.filter(
        id__in=math_ids,
        test=attempt.event.test,
    ).in_bulk()

    changed = []
    for answer in answers:
        is_correct = False
        module = module_key(answer.module)
        if answer.section == "english":
            question = english_map.get(answer.question_id)
            if question:
                is_correct = check_english_answer(question, answer.selected_answer)
                if is_correct:
                    ebrw_raw += 1
                    correct_counts["english"][module] += 1
        elif answer.section == "math":
            question = math_map.get(answer.question_id)
            if question:
                is_correct = bool(
                    answer.selected_answer is not None
                    and question.answer is not None
                    and check_written(answer.selected_answer, question.answer)
                )
                if is_correct:
                    math_raw += 1
                    correct_counts["math"][module] += 1
        if answer.is_correct != is_correct:
            answer.is_correct = is_correct
            changed.append(answer)
    if changed:
        GlobalEventAnswer.objects.bulk_update(changed, ["is_correct"])
    return ebrw_raw, math_raw, correct_counts


def calculate_attempt_breakdown(attempt):
    ebrw_raw, math_raw, correct_counts = mark_answers_and_count_correct(attempt)

    test = attempt.event.test
    test_mode = get_test_mode(test)
    scoring_type = get_event_scoring_type(test)
    totals = get_event_question_totals(test)
    english_total = totals["english"]["m1"] + totals["english"]["m2"]
    math_total = totals["math"]["m1"] + totals["math"]["m2"]
    placement_total_questions = english_total + math_total
    if not placement_total_questions:
        placement_total_questions = attempt.total_questions or 0

    if scoring_type in {"sat_standard", "sat_estimated"}:
        score_result = regular_score_from_counts(test_mode, correct_counts, totals)
        english_section = score_result["sections"].get("english")
        math_section = score_result["sections"].get("math")

        ebrw_score = english_section["score"] if english_section else None
        math_score = math_section["score"] if math_section else None
        total_score = score_result["total"]
        range_total = score_result.get("range_total")
    else:
        ebrw_score = None
        math_score = None
        total_score = 0
        range_total = None

    total_raw = ebrw_raw + math_raw
    # Preserve the existing Level 1-5 placement insight for short Guest tests,
    # but do not use its old 200-600 score scale for the SAT score itself.
    placement = (
        get_level_check_placement(total_raw, placement_total_questions)
        if scoring_type == "sat_estimated"
        else None
    )

    return {
        "ebrw_raw": ebrw_raw,
        "math_raw": math_raw,
        "total_raw": total_raw,
        "correct_counts": correct_counts,
        "ebrw_score": ebrw_score,
        "math_score": math_score,
        "total_score": total_score,
        "range_total": range_total,
        "scoring_type": scoring_type,
        "scoring_label": get_event_scoring_label(test),
        "placement": placement,
        "placement_total_questions": placement_total_questions,
    }


def apply_attempt_score(attempt, *, submit=False):
    breakdown = calculate_attempt_breakdown(attempt)

    attempt.raw_score = breakdown["ebrw_raw"] + breakdown["math_raw"]
    attempt.score = breakdown["total_score"]
    attempt.answered_questions = (
        attempt.answers.exclude(selected_answer__isnull=True)
        .exclude(selected_answer="")
        .count()
    )

    update_fields = ["raw_score", "score", "answered_questions"]

    if submit:
        attempt.status = "submitted"
        attempt.submitted_at = timezone.now()
        update_fields.extend(["status", "submitted_at"])

    attempt.save(update_fields=update_fields)
    return attempt


def finalize_attempt(attempt):
    if attempt.status == "submitted":
        apply_attempt_score(attempt, submit=False)
        return attempt

    return apply_attempt_score(attempt, submit=True)


def auto_submit_attempt(attempt):
    if attempt.status != "submitted":
        finalize_attempt(attempt)




# =========================
# Views
# =========================


def guest_entry_view(request):
    if request.method == "POST":
        full_name = " ".join(request.POST.get("full_name", "").replace("\x00", "").split())[:255]
        display_name = " ".join(request.POST.get("display_name", "").replace("\x00", "").split())[:255]
        if not full_name:
            return render(request, "sat/guest/entry.html", {"error": "Full name or nickname is required."})
        if not request.session.session_key:
            request.session.create()
        guest = GuestParticipant.objects.create(
            full_name=full_name,
            display_name=display_name,
            session_key=request.session.session_key or "",
            first_ip=get_client_ip(request),
            user_agent=request.META.get("HTTP_USER_AGENT", "")[:2000],
        )
        request.session["guest_mode"] = True
        request.session["guest_id"] = str(guest.guest_id)
        request.session["guest_name"] = guest.display_name or guest.full_name
        return redirect("global_event_list")
    if is_guest_mode(request) and get_guest_from_session(request):
        return redirect("global_event_list")
    return render(request, "sat/guest/entry.html")


def guest_logout_view(request):
    request.session.flush()
    return redirect("guest_entry")


def _serialize_sat_global_event(event, now=None):
    availability = _event_availability(event, now)
    return {
        "source": "sat",
        "source_label": "SAT",
        "title": event.title,
        "slug": event.slug,
        "description": event.description,
        "status": event.status,
        "availability": availability,
        "always_live": event.always_live,
        "start_at": event.start_at,
        "end_at": event.end_at,
        "english_duration_minutes": event.english_duration_minutes,
        "math_duration_minutes": event.math_duration_minutes,
        "detail_url": reverse("global_event_detail", kwargs={"slug": event.slug}),
    }


def _serialize_ap_global_event(request, event):
    exam = event.exam
    now = timezone.now()
    if event.is_live_now:
        availability = {"state": "live", "label": "Live now", "can_start": True}
    elif not event.always_live and event.end_at and now > event.end_at:
        availability = {"state": "ended", "label": "Ended", "can_start": False}
    elif event.start_at and now < event.start_at:
        availability = {"state": "upcoming", "label": "Upcoming", "can_start": False}
    else:
        availability = {"state": "waiting", "label": "Waiting to open", "can_start": False}
    return {
        "source": "ap",
        "source_label": "AP",
        "title": event.title,
        "slug": event.slug,
        "description": event.description or getattr(exam, "description", ""),
        "status": event.status,
        "availability": availability,
        "always_live": event.always_live,
        "start_at": event.start_at,
        "end_at": event.end_at,
        "english_duration_minutes": event.part_a_duration_minutes or getattr(exam, "part_a_duration_minutes", None),
        "math_duration_minutes": event.part_b_duration_minutes or getattr(exam, "part_b_duration_minutes", None),
        "frq_duration_minutes": event.frq_duration_minutes or getattr(exam, "frq_duration_minutes", None),
        "detail_url": reverse("apclasses:event_detail", kwargs={"slug": event.slug}),
    }


@guest_required
def global_event_list_view(request):
    now = timezone.now()
    sat_events = []
    for event in GlobalEvent.objects.filter(is_public=True, status__in=["live", "scheduled"]).select_related("test"):
        serialized = _serialize_sat_global_event(event, now)
        if serialized["availability"]["state"] not in {"ended", "unavailable"}:
            sat_events.append(serialized)

    ap_events = []
    if APExamEvent is not None:
        ap_queryset = APExamEvent.objects.select_related("exam", "exam__ap_class").filter(
            is_public=True, is_global=True, status__in=["live", "scheduled"]
        )
        ap_events = [
            item for item in (_serialize_ap_global_event(request, event) for event in ap_queryset)
            if item["availability"]["state"] not in {"ended", "unavailable"}
        ]

    events = sorted(
        chain(sat_events, ap_events),
        key=lambda item: (
            0 if item.get("availability", {}).get("state") == "live" else 1,
            0 if item.get("always_live") else 1,
            item.get("start_at") or now,
            item.get("title") or "",
        ),
    )
    return render(request, "sat/guest/event_list.html", {"events": events, "now": now})


@guest_required
def global_event_detail_view(request, slug):
    event = get_object_or_404(GlobalEvent.objects.select_related("test"), slug=slug, is_public=True)
    guest = get_guest_from_session(request)
    existing_attempt = GlobalEventAttempt.objects.filter(event=event, guest=guest).first() if guest else None
    if existing_attempt:
        _repair_guest_attempt_expiry(existing_attempt)
        if existing_attempt.status == "expired" or (
            existing_attempt.status == "in_progress"
            and (_event_hard_ended(event) or timezone.now() >= existing_attempt.expires_at)
        ):
            existing_attempt = _finalize_guest_attempt_safely(existing_attempt.pk)
    return render(request, "sat/guest/event_detail.html", {
        "event": event,
        "existing_attempt": existing_attempt,
        "availability": _event_availability(event),
    })


@guest_required
def start_global_event_view(request, slug):
    if request.method != "POST":
        return redirect("global_event_detail", slug=slug)
    event = get_object_or_404(GlobalEvent.objects.select_related("test"), slug=slug, is_public=True)
    guest = get_guest_from_session(request)
    if not guest:
        return redirect("guest_entry")

    key, _, now_ts, blocked_until = _guest_access_failure_state(request, event)
    if blocked_until > now_ts:
        messages.error(request, "Too many incorrect access-code attempts. Try again in 15 minutes.")
        return redirect("global_event_detail", slug=slug)
    if not event.is_live_now:
        messages.error(request, "This event is not available right now.")
        return redirect("global_event_detail", slug=slug)

    submitted_code = request.POST.get("access_code", "").strip()
    if event.access_code and submitted_code != event.access_code:
        _record_guest_access_failure(request, event)
        messages.error(request, "Invalid access code.")
        return redirect("global_event_detail", slug=slug)
    _clear_guest_access_failures(request, event)

    sequence = get_test_sequence(event.test)
    if not sequence:
        messages.error(request, "This test has no supported modules or questions.")
        return redirect("global_event_detail", slug=slug)

    existing_attempt = GlobalEventAttempt.objects.filter(event=event, guest=guest).first()
    if existing_attempt:
        _repair_guest_attempt_expiry(existing_attempt)
        if existing_attempt.status == "expired":
            _sync_all_guest_drafts(existing_attempt)
            finalize_attempt(existing_attempt)
            return redirect("global_event_result", guest_token=existing_attempt.guest_token)
        if existing_attempt.status == "submitted":
            return redirect("global_event_result", guest_token=existing_attempt.guest_token)
        if existing_attempt.status == "in_progress" and event.allow_resume:
            current_step = get_guest_current_step(existing_attempt)
            if current_step is None:
                finalize_attempt(existing_attempt)
                return redirect("global_event_result", guest_token=existing_attempt.guest_token)
            return redirect("global_event_attempt", guest_token=existing_attempt.guest_token)
        messages.error(request, "Another attempt is not allowed for this event.")
        return redirect("global_event_detail", slug=slug)

    total_questions = sum(len(_questions_for_step(event.test, section, module)) for section, module in sequence)
    attempt = GlobalEventAttempt.objects.create(
        event=event,
        guest=guest,
        expires_at=_guest_attempt_expiry(event, sequence),
        total_questions=total_questions,
    )
    return redirect("global_event_attempt", guest_token=attempt.guest_token)


@guest_required
def global_event_attempt_view(request, guest_token):
    attempt = get_object_or_404(
        GlobalEventAttempt.objects.select_related("event", "guest", "event__test"),
        guest_token=guest_token,
    )
    guest = get_guest_from_session(request)
    if not guest or attempt.guest_id != guest.id:
        return redirect("global_event_list")
    if attempt.status == "submitted":
        return redirect("global_event_result", guest_token=attempt.guest_token)
    if attempt.status == "expired":
        _finalize_guest_attempt_safely(attempt.pk)
        return redirect("global_event_result", guest_token=attempt.guest_token)

    _repair_guest_attempt_expiry(attempt)
    now = timezone.now()
    if _event_hard_ended(attempt.event, now) or now >= attempt.expires_at:
        _finalize_guest_attempt_safely(attempt.pk)
        return redirect("global_event_result", guest_token=attempt.guest_token)

    current_step = get_guest_current_step(attempt)
    if current_step is None:
        _finalize_guest_attempt_safely(attempt.pk)
        return redirect("global_event_result", guest_token=attempt.guest_token)
    section, module = current_step
    questions = _questions_for_step(attempt.event.test, section, module, formatted=(section == "english"))
    if not questions:
        return redirect(_complete_guest_module(attempt, section, module))

    draft = _ensure_guest_module_draft(attempt, section, module, questions)
    if _draft_remaining_seconds(draft) <= 0:
        return redirect(_complete_guest_module(attempt, section, module))

    context = {
        "attempt": attempt,
        "event": attempt.event,
        "test": attempt.event.test,
        "questions": questions,
        "section": section,
        "module": module,
        "time_left_seconds": _draft_remaining_seconds(draft),
        "custom_time_seconds": _draft_remaining_seconds(draft),
        "test_session_state": _guest_draft_state_payload(draft, questions),
        "attempt_id": attempt.guest_token,
    }
    if section == "english":
        return render(request, "sat/guest/attempt_eng.html", context)

    context["questions_data"] = [{
        "id": question.id,
        "passage": question.passage or "",
        "number": question.number,
        "question": question.question or "",
        "a": question.get_a() if hasattr(question, "get_a") else "",
        "b": question.get_b() if hasattr(question, "get_b") else "",
        "c": question.get_c() if hasattr(question, "get_c") else "",
        "d": question.get_d() if hasattr(question, "get_d") else "",
        "type": str(question.written),
        "graph": question.get_graph() if hasattr(question, "get_graph") else "",
    } for question in questions]
    return render(request, "sat/guest/attempt_math.html", context)


@guest_required
def save_global_event_answer_view(request, guest_token):
    if request.method != "POST":
        return JsonResponse({"ok": False, "error": "POST method required."}, status=405)
    guest = get_guest_from_session(request)
    try:
        payload = json.loads(request.body.decode("utf-8")) if request.body else {}
    except (TypeError, ValueError, json.JSONDecodeError):
        return JsonResponse({"ok": False, "error": "Invalid JSON"}, status=400)

    section = str(payload.get("section") or "").strip().lower()
    module = normalize_module_name(payload.get("module"))
    with transaction.atomic():
        attempt = get_object_or_404(
            GlobalEventAttempt.objects.select_for_update().select_related("event", "event__test"),
            guest_token=guest_token,
        )
        if not guest or attempt.guest_id != guest.id:
            return JsonResponse({"ok": False, "error": "Forbidden"}, status=403)
        if attempt.status != "in_progress":
            return JsonResponse({
                "ok": False,
                "error": "Attempt already closed",
                "redirect_url": reverse("global_event_result", kwargs={"guest_token": attempt.guest_token}),
            }, status=409)

        _repair_guest_attempt_expiry(attempt)
        if _event_hard_ended(attempt.event) or timezone.now() >= attempt.expires_at:
            _sync_all_guest_drafts(attempt)
            finalize_attempt(attempt)
            return JsonResponse({
                "ok": False,
                "error": "The event has ended.",
                "redirect_url": reverse("global_event_result", kwargs={"guest_token": attempt.guest_token}),
            }, status=409)

        current_step = get_guest_current_step(attempt)
        if current_step != (section, module):
            return JsonResponse({
                "ok": False,
                "error": "This module is no longer active.",
                "redirect_url": reverse("global_event_attempt", kwargs={"guest_token": attempt.guest_token}),
            }, status=409)

        draft = GlobalEventModuleDraft.objects.select_for_update().filter(
            attempt=attempt,
            section=section,
            module=module,
        ).first()
        if not draft:
            return JsonResponse({
                "ok": False,
                "error": "Open the active module before saving it.",
                "redirect_url": reverse("global_event_attempt", kwargs={"guest_token": attempt.guest_token}),
            }, status=409)
        if _draft_remaining_seconds(draft) <= 0:
            return JsonResponse({"ok": False, "error": "Time is over", "time_over": True}, status=409)

        ok, error = _persist_guest_draft_payload(attempt, draft, payload, require_complete=False)
        if not ok:
            return JsonResponse({"ok": False, "error": error}, status=400)
        remaining_seconds = _draft_remaining_seconds(draft)
        deadline_at = int(draft.deadline_at.timestamp() * 1000)
        saved_at = int((draft.updated_at or timezone.now()).timestamp() * 1000)

    return JsonResponse({
        "ok": True,
        "remaining_seconds": remaining_seconds,
        "deadline_at": deadline_at,
        "saved_at": saved_at,
    })


@guest_required
def submit_global_event_view(request, guest_token):
    if request.method != "POST":
        return JsonResponse({"ok": False, "error": "POST method required."}, status=405)
    guest = get_guest_from_session(request)
    try:
        payload = json.loads(request.body.decode("utf-8")) if request.body else {}
    except (TypeError, ValueError, json.JSONDecodeError):
        return JsonResponse({"ok": False, "error": "Invalid JSON"}, status=400)

    with transaction.atomic():
        attempt = get_object_or_404(
            GlobalEventAttempt.objects.select_for_update().select_related("event", "event__test"),
            guest_token=guest_token,
        )
        if not guest or attempt.guest_id != guest.id:
            return JsonResponse({"ok": False, "error": "Forbidden"}, status=403)
        if attempt.status == "submitted":
            return JsonResponse({"ok": True, "already_submitted": True, "redirect_url": reverse("global_event_result", kwargs={"guest_token": attempt.guest_token})})

        _repair_guest_attempt_expiry(attempt)
        if _event_hard_ended(attempt.event) or timezone.now() >= attempt.expires_at:
            _sync_all_guest_drafts(attempt)
            finalize_attempt(attempt)
            return JsonResponse({"ok": True, "redirect_url": reverse("global_event_result", kwargs={"guest_token": attempt.guest_token})})

        section = str(payload.get("section") or "").strip().lower()
        module = normalize_module_name(payload.get("module"))
        current_step = get_guest_current_step(attempt)
        if current_step != (section, module):
            if (section, module) in _completed_guest_module_pairs(attempt):
                target = reverse("global_event_result", kwargs={"guest_token": attempt.guest_token}) if get_guest_current_step(attempt) is None else reverse("global_event_attempt", kwargs={"guest_token": attempt.guest_token})
                return JsonResponse({"ok": True, "already_submitted": True, "redirect_url": target})
            return JsonResponse({"ok": False, "error": "This module is no longer active.", "redirect_url": reverse("global_event_attempt", kwargs={"guest_token": attempt.guest_token})}, status=409)

        draft = GlobalEventModuleDraft.objects.filter(attempt=attempt, section=section, module=module).first()
        if not draft:
            return JsonResponse({"ok": False, "error": "Open the active module before submitting it.", "redirect_url": reverse("global_event_attempt", kwargs={"guest_token": attempt.guest_token})}, status=409)

        submitted_after_deadline = _draft_remaining_seconds(draft) <= 0
        recovered_deadline_snapshot = False
        if "answers" in payload:
            may_persist = not submitted_after_deadline
            if submitted_after_deadline and _guest_submit_recovery_allowed(draft, payload):
                may_persist = True
                recovered_deadline_snapshot = True
            if may_persist:
                ok, error = _persist_guest_draft_payload(attempt, draft, payload, require_complete=True)
                if not ok:
                    return JsonResponse({"ok": False, "error": error}, status=400)
        redirect_url = _complete_guest_module_locked(attempt, section, module)

    return JsonResponse({
        "ok": True,
        "redirect_url": redirect_url,
        "submitted_after_deadline": submitted_after_deadline,
        "recovered_deadline_snapshot": recovered_deadline_snapshot,
    })


@guest_required
def global_event_submit_status_view(request, guest_token):
    """Return an idempotent, read-only submission status for browser recovery.

    A browser timeout does not necessarily stop Django/PostgreSQL from finishing
    the original POST.  The client polls this endpoint instead of blindly sending
    duplicate submit requests that queue behind the same row lock.
    """
    if request.method != "GET":
        return JsonResponse({"ok": False, "error": "GET method required."}, status=405)
    guest = get_guest_from_session(request)
    attempt = get_object_or_404(
        GlobalEventAttempt.objects.select_related("event", "event__test"),
        guest_token=guest_token,
    )
    if not guest or attempt.guest_id != guest.id:
        return JsonResponse({"ok": False, "error": "Forbidden"}, status=403)

    section = str(request.GET.get("section") or "").strip().lower()
    module = normalize_module_name(request.GET.get("module"))
    if section not in VALID_SECTIONS or module not in VALID_MODULES:
        return JsonResponse({"ok": False, "error": "Invalid module."}, status=400)

    result_url = reverse("global_event_result", kwargs={"guest_token": attempt.guest_token})
    if attempt.status == "submitted":
        return JsonResponse({"ok": True, "state": "completed", "redirect_url": result_url})

    completed = _completed_guest_module_pairs(attempt)
    if (section, module) in completed:
        current = get_guest_current_step(attempt)
        if current is None:
            redirect_url = result_url
        else:
            base = reverse("global_event_attempt", kwargs={"guest_token": attempt.guest_token})
            redirect_url = f"{base}?section={current[0]}&module={module_query_name(current[1])}"
        return JsonResponse({"ok": True, "state": "completed", "redirect_url": redirect_url})

    current = get_guest_current_step(attempt)
    if current == (section, module):
        draft = GlobalEventModuleDraft.objects.filter(
            attempt=attempt,
            section=section,
            module=module,
        ).only("deadline_at", "updated_at").first()
        return JsonResponse({
            "ok": True,
            "state": "pending",
            "remaining_seconds": _draft_remaining_seconds(draft) if draft else 0,
            "server_time": int(timezone.now().timestamp() * 1000),
        })

    return JsonResponse({
        "ok": True,
        "state": "moved",
        "redirect_url": reverse("global_event_attempt", kwargs={"guest_token": attempt.guest_token}),
    })


@guest_required
def global_event_result_view(request, guest_token):
    guest = get_guest_from_session(request)
    with transaction.atomic():
        attempt = get_object_or_404(
            GlobalEventAttempt.objects.select_for_update().select_related("event", "event__test", "guest"),
            guest_token=guest_token,
        )
        if not guest or attempt.guest_id != guest.id:
            return redirect("global_event_list")

        _repair_guest_attempt_expiry(attempt)
        if attempt.status == "expired":
            _sync_all_guest_drafts(attempt)
            finalize_attempt(attempt)
        elif attempt.status != "submitted":
            if has_all_required_modules(attempt):
                finalize_attempt(attempt)
            elif _event_hard_ended(attempt.event) or timezone.now() >= attempt.expires_at:
                _sync_all_guest_drafts(attempt)
                finalize_attempt(attempt)
            else:
                return redirect("global_event_attempt", guest_token=attempt.guest_token)
        else:
            apply_attempt_score(attempt, submit=False)

    breakdown = calculate_attempt_breakdown(attempt)
    test_mode = get_test_mode(attempt.event.test)
    return render(request, "sat/guest/result.html", {
        "attempt": attempt,
        "event": attempt.event,
        "test_mode": test_mode,
        "show_score": attempt.event.show_score_immediately,
        "can_review": attempt.event.show_score_immediately,
        "total_score": breakdown["total_score"],
        "ebrw_score": breakdown["ebrw_score"],
        "math_score": breakdown["math_score"],
        "range_total": breakdown["range_total"],
        "scoring_label": breakdown["scoring_label"],
        "scoring_type": breakdown["scoring_type"],
        "placement": breakdown["placement"],
        "placement_total_questions": breakdown["placement_total_questions"],
        "total_raw": breakdown["total_raw"],
        "ebrw_raw": breakdown["ebrw_raw"],
        "math_raw": breakdown["math_raw"],
    })


def _guest_review_access_or_redirect(request, guest_token):
    attempt = get_object_or_404(
        GlobalEventAttempt.objects.select_related("event", "event__test", "guest"),
        guest_token=guest_token,
    )
    guest = get_guest_from_session(request)
    if not guest or attempt.guest_id != guest.id:
        return None, redirect("global_event_list")
    if attempt.status != "submitted":
        return None, redirect("global_event_attempt", guest_token=attempt.guest_token)
    if not attempt.event.show_score_immediately:
        messages.info(
            request,
            "Question review is not available until the event owner releases scores.",
        )
        return None, redirect("global_event_result", guest_token=attempt.guest_token)
    apply_attempt_score(attempt, submit=False)
    return attempt, None


def _guest_review_rows(attempt):
    """Return the ordered guest review map without exposing per-question timing."""
    answer_map = {
        (answer.section, normalize_module_name(answer.module), answer.question_id): answer
        for answer in attempt.answers.all()
    }
    rows = []
    position = 0
    for section, module in get_test_sequence(attempt.event.test):
        questions = _questions_for_step(
            attempt.event.test,
            section,
            module,
            formatted=(section == "english"),
        )
        for question in questions:
            position += 1
            answer = answer_map.get((section, module, question.id))
            rows.append({
                "section": section,
                "module": module,
                "number": question.number or position,
                "position": position,
                "question_id": question.id,
                "selected_answer": answer.selected_answer if answer else "",
                "is_answered": bool(answer and str(answer.selected_answer or "").strip()),
                "is_correct": bool(answer and answer.is_correct),
                "review_url": reverse(
                    "global_event_review_question",
                    kwargs={
                        "guest_token": attempt.guest_token,
                        "section": section,
                        "module": module,
                        "id": question.id,
                    },
                ),
            })
    return rows


def _guest_review_groups(rows):
    groups = []
    group_map = {}
    for row in rows:
        key = (row["section"], row["module"])
        if key not in group_map:
            group = {
                "section": row["section"],
                "module": row["module"],
                "label": f'{row["section"].title()} · {row["module"].upper()}',
                "questions": [],
                "correct": 0,
                "answered": 0,
            }
            group_map[key] = group
            groups.append(group)
        group = group_map[key]
        group["questions"].append(row)
        if row["is_answered"]:
            group["answered"] += 1
        if row["is_correct"]:
            group["correct"] += 1
    return groups


@guest_required
def global_event_review_view(request, guest_token):
    attempt, response = _guest_review_access_or_redirect(request, guest_token)
    if response:
        return response

    rows = _guest_review_rows(attempt)
    correct_count = sum(1 for row in rows if row["is_correct"])
    answered_count = sum(1 for row in rows if row["is_answered"])
    return render(request, "sat/guest/review.html", {
        "attempt": attempt,
        "event": attempt.event,
        "rows": rows,
        "groups": _guest_review_groups(rows),
        "correct_count": correct_count,
        "incorrect_count": max(answered_count - correct_count, 0),
        "unanswered_count": max(len(rows) - answered_count, 0),
        "total_questions": len(rows),
        "first_review_url": rows[0]["review_url"] if rows else "",
    })


@guest_required
def global_event_review_question_view(request, guest_token, section, module, id):
    attempt, response = _guest_review_access_or_redirect(request, guest_token)
    if response:
        return response

    section = str(section or "").strip().lower()
    module = normalize_module_name(module)
    if section not in VALID_SECTIONS or module not in VALID_MODULES:
        return redirect("global_event_review", guest_token=attempt.guest_token)

    question_model = _question_model(section)
    question = get_object_or_404(
        question_model,
        pk=id,
        test=attempt.event.test,
        module=module_query_name(module),
    )
    if section == "english":
        question = list(format_english_questions_for_display([question]))[0]

    answer_obj = attempt.answers.filter(
        section=section,
        module=module,
        question_id=question.id,
    ).first()
    answered = answer_obj.selected_answer if answer_obj else ""

    rows = _guest_review_rows(attempt)
    ordered_keys = [
        (row["section"], row["module"], row["question_id"])
        for row in rows
    ]
    current_key = (section, module, question.id)
    if current_key not in ordered_keys:
        return redirect("global_event_review", guest_token=attempt.guest_token)
    current_index = ordered_keys.index(current_key)
    prev_url = rows[current_index - 1]["review_url"] if current_index > 0 else ""
    next_url = rows[current_index + 1]["review_url"] if current_index + 1 < len(rows) else ""

    question_payload = _review_question_payload(question, section)
    review_choices = _review_choices_payload(question, section)
    if section == "english":
        is_open_text = bool(getattr(question, "is_open_text", False))
        answered_choice = "" if is_open_text else _normalize_review_choice_letter(answered)
        correct_choice = "" if is_open_text else _normalize_review_choice_letter(question.answer)
        answer_is_correct = bool(answer_obj.is_correct) if answer_obj else check_english_answer(question, answered)
        template_name = "test/review/test_eng.html"
    else:
        is_written = bool(getattr(question, "written", False))
        answered_choice = "" if is_written else _normalize_review_choice_letter(answered)
        correct_choice = "" if is_written else _normalize_review_choice_letter(question.answer)
        answer_is_correct = bool(answer_obj.is_correct) if answer_obj else check_written(answered, question.answer)
        template_name = "test/review/test_math.html"

    return render(request, template_name, {
        "question": question,
        "question_payload": question_payload,
        "review_choices": review_choices,
        "answered_choice": answered_choice,
        "correct_choice": correct_choice,
        "answered": answered,
        "answer_is_correct": answer_is_correct,
        "prev": prev_url,
        "next": next_url,
        "test": attempt.event.test,
        "results_url": reverse("global_event_result", args=[attempt.guest_token]),
        "review_overview_url": reverse("global_event_review", args=[attempt.guest_token]),
        "is_guest_review": True,
        "guest_attempt": attempt,
        "guest_event": attempt.event,
        "guest_review_position": current_index + 1,
        "guest_review_total": len(rows),
    })

def _mask_guest_name(attempt):
    display = (attempt.guest.display_name or "").strip()
    if display:
        return display[:80]
    parts = (attempt.guest.full_name or "Guest").split()
    if len(parts) == 1:
        return parts[0][:1] + "***" if parts[0] else "Guest"
    return f"{parts[0]} {parts[-1][:1]}."


@guest_required
def global_event_leaderboard_view(request, slug):
    event = get_object_or_404(GlobalEvent.objects.select_related("test"), slug=slug, is_public=True)
    if not event.show_leaderboard or not event.show_score_immediately:
        messages.info(request, "The leaderboard is not available until scores are released.")
        return redirect("global_event_detail", slug=slug)
    submitted = list(event.attempts.filter(status="submitted").select_related("guest", "event", "event__test"))
    for item in submitted:
        if item.score is None:
            apply_attempt_score(item, submit=False)
        item.public_name = _mask_guest_name(item)
    submitted.sort(key=lambda item: (-(float(item.score or 0)), item.submitted_at or timezone.now()))
    return render(request, "sat/guest/leaderboard.html", {
        "event": event,
        "attempts": submitted[:100],
        "scoring_label": get_event_scoring_label(event.test),
    })
