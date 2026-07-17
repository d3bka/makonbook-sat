from __future__ import annotations

import logging
import re

from .answer_normalization import normalize_text_answer
from .placement_offline_grading import (
    check_placement_offline_answer,
    placement_offline_reference_answer,
)

logger = logging.getLogger(__name__)

def _lines(value) -> list[str]:
    return [line.strip() for line in str(value or "").splitlines() if line.strip()]


def check_english_answer(question, response) -> bool:
    """Grade English MCQ or open text without any external service."""
    if question is None:
        return False
    if getattr(question, "response_type", "multiple_choice") != "open_text":
        return normalize_text_answer(response).upper() == normalize_text_answer(question.answer).upper() and bool(normalize_text_answer(response))

    actual = normalize_text_answer(response)
    if not actual:
        return False

    # Placement Test Offline questions 1-15 use a version-controlled,
    # deterministic answer bank and local grammar rules. This branch never
    # calls OpenAI or any other external service and cannot be bypassed by a
    # stale regex saved in the database.
    placement_result = check_placement_offline_answer(question, response)
    if placement_result is not None:
        return placement_result

    accepted = _lines(getattr(question, "accepted_answers", ""))
    if question.answer:
        accepted.insert(0, str(question.answer))
    if any(actual == normalize_text_answer(candidate) for candidate in accepted):
        return True

    for pattern in _lines(getattr(question, "answer_patterns", "")):
        try:
            if re.fullmatch(pattern, actual, flags=re.IGNORECASE):
                return True
        except re.error:
            logger.warning("Ignoring invalid answer regex for English question %s: %r", getattr(question, "pk", None), pattern)
    return False


def reference_answer(question) -> str:
    placement_reference = placement_offline_reference_answer(question)
    if placement_reference is not None:
        return placement_reference
    accepted = _lines(getattr(question, "accepted_answers", ""))
    return accepted[0] if accepted else str(getattr(question, "answer", "") or "")
