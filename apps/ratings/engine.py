from __future__ import annotations

from collections import defaultdict
from datetime import datetime, time
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Iterable

from django.contrib.auth.models import User
from django.db.models import QuerySet
from django.utils import timezone

from .models import RatingAssessment, RatingConfig


CRITERIA = ("homework", "progress", "activity", "attendance", "behavior")


@dataclass(frozen=True)
class StreamResult:
    classroom_id: int
    classroom_name: str
    rating: Decimal
    assessment_count: int
    qualifies: bool


@dataclass(frozen=True)
class BoardEntry:
    rank: int
    student: User
    masked_name: str
    rating: Decimal
    assessment_count: int
    streams: tuple[StreamResult, ...]
    eligible: bool

    @property
    def student_id(self) -> int:
        return self.student.pk


def q2(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def assessment_mean(assessment: RatingAssessment) -> Decimal:
    return sum((Decimal(str(getattr(assessment, key))) for key in CRITERIA), Decimal("0")) / Decimal("5")


def month_bounds(value=None):
    value = value or timezone.localdate()
    start = value.replace(day=1)
    if start.month == 12:
        next_start = start.replace(year=start.year + 1, month=1)
    else:
        next_start = start.replace(month=start.month + 1)
    tz = timezone.get_current_timezone()
    return timezone.make_aware(datetime.combine(start, time.min), tz), timezone.make_aware(datetime.combine(next_start, time.min), tz)


def replay_stream(items: Iterable[RatingAssessment], alpha: Decimal) -> Decimal:
    rating = None
    for item in sorted(items, key=lambda row: (row.assessed_at, row.pk)):
        mean = assessment_mean(item)
        rating = mean if rating is None else alpha * mean + (Decimal("1") - alpha) * rating
    return q2(rating or Decimal("0"))


def mask_names(users: Iterable[User]) -> dict[int, str]:
    base = {}
    groups = defaultdict(list)
    for user in users:
        full = (user.get_full_name() or user.username).strip()
        parts = full.split()
        first = parts[0] if parts else user.username
        initial = parts[-1][0].upper() if len(parts) > 1 and parts[-1] else ""
        masked = f"{first} {initial}." if initial else first
        base[user.pk] = masked
        groups[masked].append(user.pk)
    result = {}
    for masked, ids in groups.items():
        for index, user_id in enumerate(sorted(ids), start=1):
            result[user_id] = masked if index == 1 else f"{masked} {index}"
    return result


def build_board(*, target_date=None, include_ineligible=False):
    config = RatingConfig.get_solo()
    start, end = month_bounds(target_date)
    qs = RatingAssessment.objects.filter(assessed_at__gte=start, assessed_at__lt=end).select_related("student", "classroom")
    grouped = defaultdict(list)
    students = {}
    for item in qs:
        grouped[(item.student_id, item.classroom_id)].append(item)
        students[item.student_id] = item.student

    masks = mask_names(students.values())
    streams_by_student = defaultdict(list)
    for (student_id, classroom_id), items in grouped.items():
        stream = StreamResult(
            classroom_id=classroom_id,
            classroom_name=items[0].classroom.name,
            rating=replay_stream(items, config.alpha),
            assessment_count=len(items),
            qualifies=len(items) >= config.min_assessments_per_classroom,
        )
        streams_by_student[student_id].append(stream)

    rows = []
    for student_id, student in students.items():
        profile = getattr(student, "rating_profile", None)
        if profile is not None and not profile.public_visible and not include_ineligible:
            continue
        streams = sorted(streams_by_student[student_id], key=lambda s: s.classroom_name.lower())
        qualifying = [s for s in streams if s.qualifies]
        eligible = len(qualifying) >= config.min_qualifying_classrooms
        source = qualifying if qualifying else streams
        rating = q2(sum((s.rating for s in source), Decimal("0")) / Decimal(len(source))) if source else Decimal("0")
        count = sum(s.assessment_count for s in streams)
        if eligible or include_ineligible:
            rows.append(BoardEntry(0, student, masks.get(student_id, student.username), rating, count, tuple(streams), eligible))

    rows.sort(key=lambda row: (-row.rating, -row.assessment_count, (row.student.get_full_name() or row.student.username).lower()))
    ranked = []
    rank = 0
    for row in rows:
        if row.eligible:
            rank += 1
            ranked.append(BoardEntry(rank, row.student, row.masked_name, row.rating, row.assessment_count, row.streams, True))
        elif include_ineligible:
            ranked.append(row)
    return ranked[: config.top_n] if not include_ineligible else ranked


def student_rating(student: User, target_date=None):
    for entry in build_board(target_date=target_date, include_ineligible=True):
        if entry.student_id == student.pk:
            return entry
    return None
