import json
from datetime import timedelta

from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.db.models import Q
from django.db import models
from django.contrib import messages
from django.http import JsonResponse
from django.urls import reverse
from itertools import chain

from .models import (
    GlobalEvent,
    GuestParticipant,
    GlobalEventAttempt,
    GlobalEventAnswer,
    English_Question,
    Math_Question,
)

# Используем существующую проверку written math из обычного SAT flow
from .views import *
from .libs import calculator
from .text_formatting import format_english_questions_for_display

try:
    from apps.apclasses.models import APExamEvent
except Exception:  # pragma: no cover
    APExamEvent = None


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
    sequence = get_test_sequence(attempt.event.test)

    try:
        index = sequence.index((section, module))
    except ValueError:
        return None

    if index == len(sequence) - 1:
        return reverse("global_event_result", kwargs={"guest_token": attempt.guest_token})

    next_section, next_module = sequence[index + 1]
    module_param = "module_1" if next_module == "m1" else "module_2"

    base = reverse("global_event_attempt", kwargs={"guest_token": attempt.guest_token})
    return f"{base}?section={next_section}&module={module_param}"

def has_all_required_modules(attempt):
    modules = set(
        attempt.answers.values_list("section", "module").distinct()
    )
    required = set(get_test_sequence(attempt.event.test))
    return required.issubset(modules)

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



PLACEMENT_TEST_NAMES = {"placement test"}

PLACEMENT_EBRW_SCORE_TABLE = {
    27: 700,
    26: 690,
    25: 680,
    24: 670,
    23: 660,
    22: 640,
    21: 630,
    20: 620,
    19: 610,
    18: 600,
    17: 590,
    16: 580,
    15: 570,
    14: 560,
    13: 540,
    12: 530,
    11: 520,
    10: 500,
    9: 470,
    8: 440,
    7: 410,
    6: 380,
    5: 350,
    4: 320,
    3: 290,
    2: 260,
    1: 230,
    0: 200,
}

PLACEMENT_MATH_SCORE_TABLE = {
    38: 750,
    37: 740,
    36: 730,
    35: 710,
    34: 700,
    33: 690,
    32: 680,
    31: 660,
    30: 650,
    29: 640,
    28: 630,
    27: 610,
    26: 600,
    25: 590,
    24: 580,
    23: 580,
    22: 570,
    21: 560,
    20: 550,
    19: 540,
    18: 530,
    17: 520,
    16: 520,
    15: 510,
    14: 500,
    13: 490,
    12: 460,
    11: 440,
    10: 410,
    9: 390,
    8: 370,
    7: 350,
    6: 330,
    5: 310,
    4: 290,
    3: 260,
    2: 240,
    1: 220,
    0: 200,
}


def is_placement_test(test_obj):
    return bool(test_obj and str(getattr(test_obj, "name", "")).strip().lower() in PLACEMENT_TEST_NAMES)


def placement_score_from_table(correct, score_table):
    try:
        correct = int(correct or 0)
    except (TypeError, ValueError):
        correct = 0

    min_correct = min(score_table.keys())
    max_correct = max(score_table.keys())
    correct = max(min_correct, min(max_correct, correct))
    return score_table[correct]


def placement_section_scores(test_mode, ebrw_raw, math_raw):
    ebrw_score = None
    math_score = None

    if test_mode in ["full", "ebrw_only"]:
        ebrw_score = placement_score_from_table(ebrw_raw, PLACEMENT_EBRW_SCORE_TABLE)

    if test_mode in ["full", "math_only"]:
        math_score = placement_score_from_table(math_raw, PLACEMENT_MATH_SCORE_TABLE)

    if test_mode == "full":
        range_total = {"lower": 400, "upper": 1600}
    else:
        range_total = {"lower": 200, "upper": 800}

    return ebrw_score, math_score, (ebrw_score or 0) + (math_score or 0), range_total


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
    """
    SAT-style scoring is safe only for sections that have two modules.
    If a Global Event has one-module/short sections, use the Level Check scale.

    Placement Test is a special guest/global event: it must use the fixed
    27-question EBRW and 38-question Math conversion tables, not Level Check.
    """
    if is_placement_test(test):
        return "placement_test"

    totals = get_event_question_totals(test)
    test_mode = get_test_mode(test)

    if test_mode == "full":
        return "sat_standard" if (
            section_has_two_modules(totals, "english")
            and section_has_two_modules(totals, "math")
        ) else "level_check"

    if test_mode == "ebrw_only":
        return "sat_standard" if section_has_two_modules(totals, "english") else "level_check"

    if test_mode == "math_only":
        return "sat_standard" if section_has_two_modules(totals, "math") else "level_check"

    return "level_check"


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

    if scoring_type == "placement_test":
        if test_mode == "full":
            return "Placement Test table scale 400–1600"
        return "Placement Test table scale 200–800"

    if scoring_type == "sat_standard":
        normalized = "" if is_standard_sat_question_count(test) else " normalized"
        if test_mode == "full":
            return f"SAT-style{normalized} 400–1600"
        return f"SAT-style{normalized} 200–800"

    if test_mode == "full":
        return "Level Check scaled 400–1200"
    return "Level Check scaled 200–600"


def scale_correct_to_calculator_total(correct, actual_total, expected_total):
    if not actual_total:
        return 0
    return (correct / actual_total) * expected_total


def normalize_counts_for_regular_calculator(correct_counts, totals):
    return {
        "english": {
            "m1": scale_correct_to_calculator_total(
                correct_counts["english"]["m1"],
                totals["english"]["m1"],
                calculator.SECTION_CONFIG["english"]["m1_total"],
            ),
            "m2": scale_correct_to_calculator_total(
                correct_counts["english"]["m2"],
                totals["english"]["m2"],
                calculator.SECTION_CONFIG["english"]["m2_total"],
            ),
        },
        "math": {
            "m1": scale_correct_to_calculator_total(
                correct_counts["math"]["m1"],
                totals["math"]["m1"],
                calculator.SECTION_CONFIG["math"]["m1_total"],
            ),
            "m2": scale_correct_to_calculator_total(
                correct_counts["math"]["m2"],
                totals["math"]["m2"],
                calculator.SECTION_CONFIG["math"]["m2_total"],
            ),
        },
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


def mark_answers_and_count_correct(attempt):
    ebrw_raw = 0
    math_raw = 0
    correct_counts = empty_correct_counts()

    answers = attempt.answers.all()

    for ans in answers:
        is_correct = False
        module = module_key(ans.module)

        if ans.section == "english":
            question = English_Question.objects.filter(id=ans.question_id).first()
            if question:
                is_correct = normalize_answer(ans.selected_answer) == normalize_answer(question.answer)
                if is_correct:
                    ebrw_raw += 1
                    correct_counts["english"][module] += 1

        elif ans.section == "math":
            question = Math_Question.objects.filter(id=ans.question_id).first()
            if question:
                selected_answer = ans.selected_answer
                correct_answer = question.answer
                is_correct = (
                    selected_answer is not None
                    and correct_answer is not None
                    and check_written(selected_answer, correct_answer)
                )
                if is_correct:
                    math_raw += 1
                    correct_counts["math"][module] += 1

        if ans.is_correct != is_correct:
            ans.is_correct = is_correct
            ans.save(update_fields=["is_correct"])

    return ebrw_raw, math_raw, correct_counts


def calculate_attempt_breakdown(attempt):
    ebrw_raw, math_raw, correct_counts = mark_answers_and_count_correct(attempt)

    test = attempt.event.test
    test_mode = get_test_mode(test)
    scoring_type = get_event_scoring_type(test)
    totals = get_event_question_totals(test)

    if scoring_type == "placement_test":
        ebrw_score, math_score, total_score, range_total = placement_section_scores(
            test_mode,
            ebrw_raw,
            math_raw,
        )
    elif scoring_type == "sat_standard":
        score_result = regular_score_from_counts(test_mode, correct_counts, totals)
        english_section = score_result["sections"].get("english")
        math_section = score_result["sections"].get("math")

        ebrw_score = english_section["score"] if english_section else None
        math_score = math_section["score"] if math_section else None
        total_score = score_result["total"]
        range_total = score_result.get("range_total")
    else:
        english_total = totals["english"]["m1"] + totals["english"]["m2"]
        math_total = totals["math"]["m1"] + totals["math"]["m2"]
        ebrw_score = level_check_score(ebrw_raw, english_total) if test_mode in ["full", "ebrw_only"] else None
        math_score = level_check_score(math_raw, math_total) if test_mode in ["full", "math_only"] else None
        total_score = (ebrw_score or 0) + (math_score or 0)
        range_total = None

    return {
        "ebrw_raw": ebrw_raw,
        "math_raw": math_raw,
        "correct_counts": correct_counts,
        "ebrw_score": ebrw_score,
        "math_score": math_score,
        "total_score": total_score,
        "range_total": range_total,
        "scoring_type": scoring_type,
        "scoring_label": get_event_scoring_label(test),
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
        request.session["guest_name"] = guest.full_name

        return redirect("global_event_list")

    return render(request, "sat/guest/entry.html")


def guest_logout_view(request):
    request.session.flush()
    return redirect("guest_entry")


def _serialize_sat_global_event(event):
    return {
        "source": "sat",
        "source_label": "SAT",
        "title": event.title,
        "slug": event.slug,
        "description": event.description,
        "status": event.status,
        "always_live": event.always_live,
        "start_at": event.start_at,
        "end_at": event.end_at,
        "english_duration_minutes": event.english_duration_minutes,
        "math_duration_minutes": event.math_duration_minutes,
        "detail_url": reverse("global_event_detail", kwargs={"slug": event.slug}),
    }


def _serialize_ap_global_event(request, event):
    exam = event.exam

    detail_url = reverse("apclasses:event_detail", kwargs={"slug": event.slug})

    return {
        "source": "ap",
        "source_label": "AP",
        "title": event.title,
        "slug": event.slug,
        "description": event.description or getattr(exam, "description", ""),
        "status": event.status,
        "always_live": event.always_live,
        "start_at": event.start_at,
        "end_at": event.end_at,
        "english_duration_minutes": getattr(exam, "part_a_duration_minutes", None),
        "math_duration_minutes": getattr(exam, "part_b_duration_minutes", None),
        "frq_duration_minutes": getattr(exam, "frq_duration_minutes", None),
        "detail_url": detail_url,
    }


@guest_required
def global_event_list_view(request):
    now = timezone.now()

    sat_events = [
        _serialize_sat_global_event(event)
        for event in GlobalEvent.objects.filter(is_public=True).filter(
            Q(status="live") | Q(status="scheduled")
        )
    ]

    ap_events = []
    if APExamEvent is not None:
        ap_queryset = (
            APExamEvent.objects.select_related("exam", "exam__ap_class")
            .filter(is_public=True, is_global=True)
            .filter(Q(status="live") | Q(status="scheduled"))
        )
        ap_events = [_serialize_ap_global_event(request, event) for event in ap_queryset]

    events = sorted(
        chain(sat_events, ap_events),
        key=lambda event: (
            0 if event.get("always_live") else 1,
            event.get("start_at") or now,
            event.get("title") or "",
        ),
    )

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

    sequence = get_test_sequence(event.test)
    if not sequence:
        messages.error(request, "This test has no valid sections.")
        return redirect("global_event_detail", slug=slug)

    first_section, first_module = sequence[0]
    first_module_param = "module_1" if first_module == "m1" else "module_2"

    existing_attempt = GlobalEventAttempt.objects.filter(
        event=event,
        guest=guest
    ).first()

    if existing_attempt:
        if existing_attempt.status == "submitted":
            return redirect("global_event_result", guest_token=existing_attempt.guest_token)

        if existing_attempt.status == "in_progress" and event.allow_resume:
            current_step = get_guest_current_step(existing_attempt)
            if current_step is None:
                return redirect("global_event_result", guest_token=existing_attempt.guest_token)

            current_section, current_module = current_step
            current_module_param = "module_1" if current_module == "m1" else "module_2"

            return redirect(
                f"{reverse('global_event_attempt', kwargs={'guest_token': existing_attempt.guest_token})}"
                f"?section={current_section}&module={current_module_param}"
            )

        messages.error(request, "Another attempt is not allowed.")
        return redirect("global_event_detail", slug=slug)

    total_questions = 0
    for section, module in sequence:
        module_db = module_query_name(module)
        if section == "english":
            total_questions += English_Question.objects.filter(
                test=event.test,
                module=module_db
            ).count()
        elif section == "math":
            total_questions += Math_Question.objects.filter(
                test=event.test,
                module=module_db
            ).count()

    attempt = GlobalEventAttempt.objects.create(
        event=event,
        guest=guest,
        expires_at=event.end_at,
        current_module_started_at=now,
        total_questions=total_questions,
    )

    return redirect(
        f"{reverse('global_event_attempt', kwargs={'guest_token': attempt.guest_token})}"
        f"?section={first_section}&module={first_module_param}"
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

    test = attempt.event.test

    current_step = get_guest_current_step(attempt)
    if current_step is None:
        return redirect("global_event_result", guest_token=attempt.guest_token)

    if attempt.get_time_left_seconds(current_step[0]) <= 0:
        auto_submit_attempt(attempt)
        return redirect("global_event_result", guest_token=attempt.guest_token)

    default_section, default_module = current_step
    default_module_param = "module_1" if default_module == "m1" else "module_2"

    section = request.GET.get("section", default_section)
    module = request.GET.get("module", default_module_param)
    module_db = module_query_name(module)
    normalized_module = normalize_module_name(module)

    valid_steps = set(get_test_sequence(test))
    if (section, normalized_module) not in valid_steps:
        section = default_section
        module = default_module_param
        module_db = module_query_name(module)

    if section == "english":
        questions = English_Question.objects.filter(
            test=test,
            module=module_db
        ).order_by("number")

        questions = format_english_questions_for_display(questions)

        return render(request, "sat/guest/attempt_eng.html", {
            "attempt": attempt,
            "event": attempt.event,
            "test": test,
            "questions": questions,
            "section": section,
            "module": module,
            "time_left_seconds": attempt.get_time_left_seconds(section),
            "custom_time_seconds": attempt.get_time_left_seconds(section),
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
            "time_left_seconds": attempt.get_time_left_seconds(section),
            "custom_time_seconds": attempt.get_time_left_seconds(section),
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

    if request.content_type and "application/json" in request.content_type:
        try:
            payload = json.loads(request.body.decode("utf-8")) if request.body else {}
        except Exception:
            payload = {}
    else:
        payload = {}

    section = payload.get("section")
    if not section:
        current_step = get_guest_current_step(attempt)
        section = current_step[0] if current_step else None

    if attempt.get_time_left_seconds(section) <= 0:
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

    if attempt.status != "in_progress":
        return JsonResponse({"ok": False, "error": "Attempt already closed"}, status=400)

    if attempt.time_left_seconds <= 0:
        auto_submit_attempt(attempt)
        return JsonResponse({
            "ok": True,
            "redirect_url": reverse("global_event_result", kwargs={"guest_token": attempt.guest_token})
        })

    try:
        payload = json.loads(request.body.decode("utf-8")) if request.body else {}
    except Exception:
        payload = {}

    section = payload.get("section")
    module = normalize_module_name(payload.get("module"))

    valid_steps = set(get_test_sequence(attempt.event.test))
    if (section, module) not in valid_steps:
        return JsonResponse(
            {"ok": False, "error": f"Invalid section/module: {section} / {module}"},
            status=400
        )

    redirect_url = next_module_redirect_url(attempt, section, module)
    if not redirect_url:
        return JsonResponse({"ok": False, "error": "Could not determine next step"}, status=400)

    result_url = reverse("global_event_result", kwargs={"guest_token": attempt.guest_token})
    if redirect_url == result_url:
        finalize_attempt(attempt)
    else:
        # Reset the module timer when moving to the next module
        attempt.current_module_started_at = timezone.now()
        attempt.save(update_fields=["current_module_started_at"])

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

    # Always refresh the score. This updates old submitted Global Event attempts
    # that were scored with the previous Level Check-only converter.
    finalize_attempt(attempt)

    breakdown = calculate_attempt_breakdown(attempt)
    review_questions, has_english, has_math = get_guest_review_questions(attempt)

    return render(request, "sat/guest/result.html", {
        "attempt": attempt,
        "event": attempt.event,
        "show_score": attempt.event.show_score_immediately,

        "total_score": breakdown["total_score"],
        "ebrw_score": breakdown["ebrw_score"],
        "math_score": breakdown["math_score"],
        "range_total": breakdown["range_total"],
        "scoring_label": breakdown["scoring_label"],
        "scoring_type": breakdown["scoring_type"],

        # если захочешь где-то показать raw
        "ebrw_raw": breakdown["ebrw_raw"],
        "math_raw": breakdown["math_raw"],

        "review_questions": review_questions,
        "has_english": has_english,
        "has_math": has_math,
    })


def get_guest_review_questions(attempt):
    """Build the same green/red question boxes used by regular SAT results."""
    mark_answers_and_count_correct(attempt)

    test = attempt.event.test
    answer_map = {
        (answer.section, module_key(answer.module), answer.question_id): answer
        for answer in attempt.answers.all()
    }

    review_questions = {
        "english": {"m1": [], "m2": []},
        "math": {"m1": [], "m2": []},
    }

    for section, module in get_test_sequence(test):
        module_db = module_query_name(module)

        if section == "english":
            queryset = English_Question.objects.filter(test=test, module=module_db).order_by("number")
        elif section == "math":
            queryset = Math_Question.objects.filter(test=test, module=module_db).order_by("number")
        else:
            continue

        for question in queryset:
            answer = answer_map.get((section, module, question.id))
            status = "correct" if answer and answer.is_correct is True else "incorrect"
            review_questions[section][module].append({
                "id": question.id,
                "number": question.number,
                "status": status,
            })

    has_english = bool(review_questions["english"]["m1"] or review_questions["english"]["m2"])
    has_math = bool(review_questions["math"]["m1"] or review_questions["math"]["m2"])

    return review_questions, has_english, has_math


@guest_required
def global_event_review_question_view(request, guest_token, section, module, question_id):
    attempt = get_object_or_404(
        GlobalEventAttempt.objects.select_related("event", "guest", "event__test"),
        guest_token=guest_token,
    )

    guest = get_guest_from_session(request)
    if not guest or attempt.guest_id != guest.id:
        return redirect("global_event_list")

    if attempt.status != "submitted" or not attempt.event.show_score_immediately:
        return redirect("global_event_result", guest_token=attempt.guest_token)

    finalize_attempt(attempt)

    section = str(section).lower().strip()
    module = module_key(module)
    if section not in ["english", "math"] or module not in ["m1", "m2"]:
        return redirect("global_event_result", guest_token=attempt.guest_token)

    test = attempt.event.test
    module_db = module_query_name(module)

    if section == "english":
        question = English_Question.objects.filter(id=question_id, test=test, module=module_db).first()
        module_questions = list(English_Question.objects.filter(test=test, module=module_db).order_by("number"))
    else:
        question = Math_Question.objects.filter(id=question_id, test=test, module=module_db).first()
        module_questions = list(Math_Question.objects.filter(test=test, module=module_db).order_by("number"))

    if not question:
        return redirect("global_event_result", guest_token=attempt.guest_token)

    answer_obj = attempt.answers.filter(
        section=section,
        module=module,
        question_id=question.id,
    ).first()
    answered = answer_obj.selected_answer if answer_obj else ""

    ids = [q.id for q in module_questions]
    try:
        current_index = ids.index(question.id)
    except ValueError:
        current_index = 0

    def review_url(target_question_id):
        return reverse("global_event_review_question", kwargs={
            "guest_token": attempt.guest_token,
            "section": section,
            "module": module,
            "question_id": target_question_id,
        })

    prev_url = review_url(ids[current_index - 1]) if current_index > 0 else ""
    next_url = review_url(ids[current_index + 1]) if current_index < len(ids) - 1 else ""
    result_url = reverse("global_event_result", kwargs={"guest_token": attempt.guest_token})

    template_name = "test/review/test_eng.html" if section == "english" else "test/review/test_math.html"
    return render(request, template_name, {
        "question": question,
        "answered": answered,
        "prev": prev_url,
        "next": next_url,
        "test": test,
        "attempt": attempt,
        "event": attempt.event,
        "is_guest_review": True,
        "guest_result_url": result_url,
        "results_url": result_url,
    })


@guest_required
def global_event_leaderboard_view(request, slug):
    event = get_object_or_404(GlobalEvent, slug=slug, is_public=True)

    if not event.show_leaderboard:
        return redirect("global_event_detail", slug=slug)

    # Re-score before ordering so old submitted Full SAT attempts do not stay
    # stuck with the previous max-1200 Global Event score.
    for submitted_attempt in event.attempts.filter(status="submitted").select_related("event", "event__test"):
        apply_attempt_score(submitted_attempt, submit=False)

    attempts = (
        event.attempts
        .filter(status="submitted")
        .select_related("guest")
        .order_by("-score", "submitted_at")[:100]
    )

    return render(request, "sat/guest/leaderboard.html", {
        "event": event,
        "attempts": attempts,
        "scoring_label": get_event_scoring_label(event.test),
    })

def get_guest_current_step(attempt):
    sequence = get_test_sequence(attempt.event.test)

    if not sequence:
        return None

    # how many distinct section/module pairs already submitted
    completed_pairs = []
    for section, module in sequence:
        has_answers = attempt.answers.filter(
            section=section,
            module=module
        ).exclude(selected_answer__isnull=True).exclude(selected_answer='').exists()

        if has_answers:
            completed_pairs.append((section, module))
        else:
            break

    next_index = len(completed_pairs)

    if next_index >= len(sequence):
        return None

    return sequence[next_index]