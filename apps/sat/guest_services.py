from django.utils import timezone
from django.db import transaction
from .models import *

def calculate_attempt_score(attempt):
    answers = attempt.answers.select_related("question", "selected_choice")
    raw_score = 0

    for answer in answers:
        correct_choice = answer.question.choices.filter(is_correct=True).first()
        is_correct = bool(
            answer.selected_choice_id and
            correct_choice and
            answer.selected_choice_id == correct_choice.id
        )
        answer.is_correct = is_correct
        answer.save(update_fields=["is_correct"])

        if is_correct:
            raw_score += 1

    return raw_score, float(raw_score)


@transaction.atomic
def finalize_attempt(attempt):
    if attempt.status == "submitted":
        return attempt

    raw_score, final_score = calculate_attempt_score(attempt)

    attempt.raw_score = raw_score
    attempt.score = final_score
    attempt.status = "submitted"
    attempt.submitted_at = timezone.now()
    attempt.answered_questions = attempt.answers.exclude(selected_choice__isnull=True).count()
    attempt.save(
        update_fields=[
            "raw_score",
            "score",
            "status",
            "submitted_at",
            "answered_questions",
        ]
    )
    return attempt


def auto_submit_attempt(attempt):
    if attempt.status != "submitted":
        attempt.status = "expired"
        attempt.save(update_fields=["status"])
        finalize_attempt(attempt)

def is_guest_mode(request):
    return bool(request.session.get("guest_mode") and request.session.get("guest_id"))

def get_guest_from_session(request):
    guest_id = request.session.get("guest_id")
    if not guest_id:
        return None
    try:
        return GuestParticipant.objects.get(guest_id=guest_id)
    except GuestParticipant.DoesNotExist:
        return None