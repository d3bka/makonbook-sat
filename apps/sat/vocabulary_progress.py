from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from django.db import transaction
from django.db.models import Max, Sum
from django.utils import timezone

from .models import (
    StudentProgress,
    VocabularyQuizAttempt,
    VocabularyUnit,
    VocabularyWord,
    VocabularyWordProgress,
)


def _scope_filter(user, classroom=None):
    return {
        'user': user,
        'classroom': classroom,
    }


def _active_words_queryset():
    return VocabularyWord.objects.filter(is_active=True, unit__is_active=True)


def _derive_status(progress: VocabularyWordProgress) -> str:
    attempts = progress.correct_count + progress.incorrect_count
    accuracy = (progress.correct_count / attempts) if attempts else 0

    if progress.consecutive_correct >= 2 or (attempts >= 4 and accuracy >= 0.8):
        return VocabularyWordProgress.STATUS_MASTERED
    if progress.times_seen > 0:
        return VocabularyWordProgress.STATUS_LEARNING
    return VocabularyWordProgress.STATUS_NEW


@transaction.atomic
def record_word_review(*, user, word, classroom=None, outcome: str):
    """Persist a flashcard/quiz interaction and return the updated progress row.

    outcome values:
    - known / correct: positive recall
    - learning / again / incorrect: not yet recalled
    """
    progress, _ = VocabularyWordProgress.objects.select_for_update().get_or_create(
        user=user,
        classroom=classroom,
        word=word,
    )

    previous_status = progress.status
    now_value = timezone.now()
    progress.times_seen += 1
    progress.last_reviewed_at = now_value

    if outcome in {'known', 'correct'}:
        progress.correct_count += 1
        progress.consecutive_correct += 1
    else:
        progress.incorrect_count += 1
        progress.consecutive_correct = 0

    next_status = _derive_status(progress)
    if next_status == VocabularyWordProgress.STATUS_MASTERED:
        progress.mastered_at = progress.mastered_at or now_value
    elif progress.status == VocabularyWordProgress.STATUS_MASTERED:
        # A later miss moves the word back into active learning.
        progress.mastered_at = None

    progress.status = next_status
    progress.save()
    # Transient metadata used by the fast classroom progress synchronizer.
    # It avoids re-aggregating every vocabulary row on each flashcard click.
    progress._previous_status = previous_status
    return progress


def get_vocabulary_summary(user, classroom=None):
    total_words = _active_words_queryset().count()
    progress_qs = VocabularyWordProgress.objects.filter(**_scope_filter(user, classroom))

    aggregates = progress_qs.aggregate(
        reviews=Sum('times_seen'),
        correct=Sum('correct_count'),
        incorrect=Sum('incorrect_count'),
        last_reviewed=Max('last_reviewed_at'),
    )

    studied_words = progress_qs.filter(times_seen__gt=0).count()
    mastered_words = progress_qs.filter(status=VocabularyWordProgress.STATUS_MASTERED).count()
    learning_words = progress_qs.filter(status=VocabularyWordProgress.STATUS_LEARNING).count()
    reviews = aggregates['reviews'] or 0
    correct = aggregates['correct'] or 0
    incorrect = aggregates['incorrect'] or 0
    answer_total = correct + incorrect
    accuracy = round((correct / answer_total) * 100, 1) if answer_total else 0
    mastery_percent = round((mastered_words / total_words) * 100, 2) if total_words else 0
    studied_percent = round((studied_words / total_words) * 100, 2) if total_words else 0

    attempts_qs = VocabularyQuizAttempt.objects.filter(**_scope_filter(user, classroom))
    quiz_count = attempts_qs.count()
    latest_attempt = attempts_qs.first()
    best_attempt = attempts_qs.order_by('-percentage', '-completed_at').first()
    attempt_aggregates = attempts_qs.aggregate(last_quiz=Max('completed_at'))

    last_activity_candidates = [
        aggregates['last_reviewed'],
        attempt_aggregates['last_quiz'],
    ]
    last_activity = max((value for value in last_activity_candidates if value), default=None)

    return {
        'total_words': total_words,
        'studied_words': studied_words,
        'mastered_words': mastered_words,
        'learning_words': learning_words,
        'unseen_words': max(total_words - studied_words, 0),
        'review_count': reviews,
        'correct_count': correct,
        'incorrect_count': incorrect,
        'accuracy_percent': accuracy,
        'completion_percent': mastery_percent,
        'studied_percent': studied_percent,
        'quiz_count': quiz_count,
        'latest_quiz_percent': float(latest_attempt.percentage) if latest_attempt else None,
        'best_quiz_percent': float(best_attempt.percentage) if best_attempt else None,
        'last_activity_at': last_activity,
    }


def build_unit_progress_rows(user, classroom=None, units=None, include_words=False):
    units = list(units or VocabularyUnit.objects.filter(is_active=True).prefetch_related('words').order_by('order', 'id'))
    progress_qs = VocabularyWordProgress.objects.filter(
        **_scope_filter(user, classroom),
        word__unit__in=units,
    ).select_related('word', 'word__unit')
    progress_by_word = {row.word_id: row for row in progress_qs}

    rows = []
    for unit in units:
        active_words = [word for word in unit.words.all() if word.is_active]
        word_count = len(active_words)
        studied = 0
        mastered = 0
        learning = 0
        correct = 0
        incorrect = 0
        last_activity = None
        word_rows = []

        for word in active_words:
            progress = progress_by_word.get(word.id)
            status = progress.status if progress else VocabularyWordProgress.STATUS_NEW
            if progress and progress.times_seen > 0:
                studied += 1
            if status == VocabularyWordProgress.STATUS_MASTERED:
                mastered += 1
            elif status == VocabularyWordProgress.STATUS_LEARNING:
                learning += 1
            if progress:
                correct += progress.correct_count
                incorrect += progress.incorrect_count
                if progress.last_reviewed_at and (not last_activity or progress.last_reviewed_at > last_activity):
                    last_activity = progress.last_reviewed_at

            if include_words:
                word_rows.append({
                    'word': word,
                    'status': status,
                    'times_seen': progress.times_seen if progress else 0,
                    'accuracy_percent': progress.accuracy_percent if progress else 0,
                    'correct_count': progress.correct_count if progress else 0,
                    'incorrect_count': progress.incorrect_count if progress else 0,
                })

        answer_total = correct + incorrect
        rows.append({
            'unit': unit,
            'word_count': word_count,
            'studied_words': studied,
            'mastered_words': mastered,
            'learning_words': learning,
            'unseen_words': max(word_count - studied, 0),
            'mastery_percent': round((mastered / word_count) * 100, 1) if word_count else 0,
            'studied_percent': round((studied / word_count) * 100, 1) if word_count else 0,
            'accuracy_percent': round((correct / answer_total) * 100, 1) if answer_total else 0,
            'last_activity_at': last_activity,
            'words': word_rows,
        })
    return rows


def get_weak_words(user, classroom=None, limit=12):
    rows = list(
        VocabularyWordProgress.objects.filter(
            **_scope_filter(user, classroom),
            times_seen__gt=0,
        )
        .exclude(status=VocabularyWordProgress.STATUS_MASTERED)
        .select_related('word', 'word__unit')
        .order_by('-incorrect_count', 'correct_count', '-last_reviewed_at')[:limit]
    )
    return [
        {
            'progress': row,
            'word': row.word,
            'unit': row.word.unit,
            'accuracy_percent': row.accuracy_percent,
        }
        for row in rows
    ]


@transaction.atomic
def sync_vocabulary_review_progress(classroom, student, progress):
    """Update classroom progress incrementally after one flashcard review.

    The old endpoint recalculated every vocabulary aggregate after every 1/2/3
    click. That made the UI wait on several full-table queries. A complete
    recalculation is still used when the row does not exist, while normal
    reviews update only the counters affected by this interaction.
    """
    record = StudentProgress.objects.select_for_update().filter(
        classroom=classroom,
        student=student,
        section='vocabulary',
    ).first()

    if record is None:
        return sync_vocabulary_student_progress(classroom, student)

    previous_status = getattr(
        progress,
        '_previous_status',
        VocabularyWordProgress.STATUS_NEW,
    )
    mastered_now = progress.status == VocabularyWordProgress.STATUS_MASTERED
    mastered_before = previous_status == VocabularyWordProgress.STATUS_MASTERED
    mastered_delta = int(mastered_now) - int(mastered_before)

    total_items = record.total_items or _active_words_queryset().count()
    completed_items = max(0, min(total_items, record.completed_items + mastered_delta))
    completion_percent = (
        Decimal(completed_items * 100) / Decimal(total_items)
        if total_items else Decimal('0')
    )

    record.total_items = total_items
    record.completed_items = completed_items
    record.completion_percent = completion_percent.quantize(Decimal('0.01'))
    record.activity_count += 1
    record.last_activity_at = progress.last_reviewed_at or timezone.now()
    record.save(update_fields=[
        'total_items',
        'completed_items',
        'completion_percent',
        'activity_count',
        'last_activity_at',
    ])
    return record


def sync_vocabulary_student_progress(classroom, student):
    summary = get_vocabulary_summary(student, classroom=classroom)
    StudentProgress.objects.update_or_create(
        classroom=classroom,
        student=student,
        section='vocabulary',
        defaults={
            'completion_percent': Decimal(str(summary['completion_percent'])),
            'completed_items': summary['mastered_words'],
            'total_items': summary['total_words'],
            'activity_count': summary['review_count'] + summary['quiz_count'],
            'last_activity_at': summary['last_activity_at'],
        },
    )
    return summary
