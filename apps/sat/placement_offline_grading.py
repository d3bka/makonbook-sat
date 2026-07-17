from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable

from .answer_normalization import normalize_text_answer


PLACEMENT_OFFLINE_TEST_NAME = "Placement Test Offline"
OPEN_WRITING_QUESTION_NUMBERS = frozenset(range(1, 16))


@dataclass(frozen=True)
class PlacementAnswerRule:
    reference: str
    accepted: tuple[str, ...]
    matcher: Callable[[str], bool]
    note: str = ""


_MARKUP_RE = re.compile(r"</?u\b[^>]*>|</?(?:strong|b|em|i)\b[^>]*>", re.IGNORECASE)
_WORD_RE = re.compile(r"[a-z]+(?:'[a-z]+)?")


def _canonical(value: str) -> str:
    """Normalize harmless differences for the offline placement answer bank."""
    text = _MARKUP_RE.sub(" ", str(value or ""))
    # Students may imitate the PDF's underlining instruction with markdown/plain underscores.
    text = text.replace("_", " ").replace("*", " ")
    text = normalize_text_answer(text)
    substitutions = (
        (r"\bit's\b", "it is"),
        (r"\bthere's\b", "there is"),
        (r"\bwouldn't\b", "would not"),
        (r"\bwon't\b", "will not"),
        (r"\bcan't\b", "cannot"),
        (r"\bi'll\b", "i will"),
        (r"\bwe'll\b", "we will"),
        (r"\bthey'll\b", "they will"),
        (r"\bhe'll\b", "he will"),
        (r"\bshe'll\b", "she will"),
    )
    for pattern, replacement in substitutions:
        text = re.sub(pattern, replacement, text)
    return re.sub(r"\s+", " ", text).strip()


def _fullmatch_any(text: str, patterns: tuple[str, ...]) -> bool:
    return any(re.fullmatch(pattern, text, flags=re.IGNORECASE) for pattern in patterns)


def _exact_or_pattern(accepted: tuple[str, ...], *patterns: str) -> Callable[[str], bool]:
    accepted_normalized = frozenset(_canonical(item) for item in accepted)

    def matcher(text: str) -> bool:
        return text in accepted_normalized or _fullmatch_any(text, tuple(patterns))

    return matcher


_Q1 = (
    "The scientist's analysis of the data was very careful.",
    "The scientist's analysis of the data was conducted with great care.",
    "The scientist conducted a careful analysis of the data.",
    "The scientist conducted an analysis of the data with great care.",
    "The scientist performed a careful analysis of the data.",
    "The scientist performed an analysis of the data with great care.",
    "The scientist carried out a careful analysis of the data.",
    "A careful analysis of the data was conducted by the scientist.",
)

_Q2 = (
    "Migratory birds migrate every autumn.",
    "Migratory birds travel south every autumn.",
    "Colorful birds migrate every winter.",
    "Beautiful birds migrate every year.",
    "Young birds fly south each autumn.",
    "Wild birds migrate during the winter.",
    "Small birds travel south every fall.",
    "Large birds migrate each spring.",
)

_Q3 = (
    "She walks to school every day.",
    "Every day, she walks to school.",
)

_Q4 = (
    "The train had left before we arrived at the station.",
    "The train had already left before we arrived at the station.",
    "By the time we arrived at the station, the train had left.",
    "By the time we arrived at the station, the train had already left.",
    "When we arrived at the station, the train had already left.",
    "After the train had left, we arrived at the station.",
)

_Q5 = (
    "It is going to rain.",
    "It is going to rain soon.",
    "It is going to storm.",
    "There is going to be a storm.",
    "There is going to be a thunderstorm.",
    "The weather is going to get worse.",
    "Those dark clouds are going to bring rain.",
)

_Q6 = (
    "Walking to the store, I got my jacket soaked.",
    "Walking to the store, I got my jacket soaked by the rain.",
    "Walking to the store, I was soaked by the rain.",
    "Walking to the store, I was caught in the rain.",
    "While I was walking to the store, the rain soaked my jacket.",
    "As I was walking to the store, the rain soaked my jacket.",
    "The rain soaked my jacket while I was walking to the store.",
)

_Q7 = (
    "Although the team practiced hard, they lost the final.",
    "Although they practiced hard, the team lost the final.",
    "The team lost the final although they practiced hard.",
    "Although the team had practiced hard, they lost the final.",
)

_Q8 = (
    "She said that she would finish the project the next day.",
    "She said she would finish the project the next day.",
    "She said that she would finish the project the following day.",
    "She said she would finish the project the following day.",
    "She said that she would complete the project the next day.",
    "She said that she would complete the project the following day.",
)

_Q9 = (
    "Exercising every morning is healthy.",
    "Doing exercise every morning is healthy.",
    "Working out every morning is healthy.",
    "Getting exercise every morning is healthy.",
    "Exercising every morning is good for your health.",
    "Working out each morning is beneficial for your health.",
)

_Q10 = (
    "She studies hard to pass the exam.",
    "She studies hard in order to pass the exam.",
    "She studies hard so as to pass the exam.",
    "To pass the exam, she studies hard.",
    "In order to pass the exam, she studies hard.",
    "She works hard to pass the exam.",
    "She studies diligently to pass the exam.",
)

_Q11 = (
    "If it rains tomorrow, we will cancel the picnic.",
    "If it rains tomorrow, I will stay home.",
    "If it rains tomorrow, we will stay inside.",
    "If it rains tomorrow, we will take an umbrella.",
    "If it rains tomorrow, I will take an umbrella.",
    "If it rains tomorrow, I will wear a raincoat.",
    "If it rains tomorrow, we will postpone the trip.",
    "If it rains tomorrow, the match will be canceled.",
    "If it rains tomorrow, the game will be postponed.",
    "If it rains tomorrow, we will not go outside.",
    "If it rains tomorrow, the streets will be wet.",
    "If it rains tomorrow, the roads will be slippery.",
)

_Q12 = (
    "If he had studied, he would not have failed the test.",
    "He would not have failed the test if he had studied.",
    "Had he studied, he would not have failed the test.",
    "If he had studied harder, he would not have failed the test.",
    "If he had studied, he might not have failed the test.",
)

_Q13 = (
    "Have you?",
    "Have you",
    "You haven't finished your homework, have you?",
)

_Q14 = (
    "Could you tell me where the train station is?",
    "Could you tell me where the train station is, please?",
    "Could you please tell me where the train station is?",
)

_Q15 = (
    "The results will be announced by the committee on Friday.",
    "The results will be announced on Friday.",
    "On Friday, the results will be announced by the committee.",
    "On Friday, the results will be announced.",
)


_ADJECTIVES = frozenset({
    "beautiful", "colorful", "colourful", "graceful", "large", "little", "migratory",
    "native", "northern", "seasonal", "small", "southern", "strong", "tiny", "tropical",
    "wild", "young",
})
_MIGRATION_VERBS = frozenset({"fly", "head", "migrate", "move", "return", "travel"})
_TIME_PATTERNS = (
    r"\bevery (?:day|year|spring|summer|autumn|fall|winter|morning|season|october)\b",
    r"\beach (?:day|year|spring|summer|autumn|fall|winter|morning|season)\b",
    r"\bduring (?:the )?(?:spring|summer|autumn|fall|winter|morning|evening|night)\b",
    r"\bin (?:the )?(?:spring|summer|autumn|fall|winter|morning|evening|night)\b",
    r"\b(?:annually|daily|seasonally|today|tonight|yearly)\b",
)


def _match_q2(text: str) -> bool:
    if text in {_canonical(item) for item in _Q2}:
        return True
    words = _WORD_RE.findall(text)
    try:
        birds_index = words.index("birds")
    except ValueError:
        return False
    if birds_index < 1 or words[birds_index - 1] not in _ADJECTIVES:
        return False
    if not any(word in _MIGRATION_VERBS for word in words[birds_index + 1:]):
        return False
    return any(re.search(pattern, text) for pattern in _TIME_PATTERNS)


def _match_q5(text: str) -> bool:
    if text in {_canonical(item) for item in _Q5}:
        return True
    patterns = (
        r"(?:it|the weather|the sky) is going to (?:rain|storm|pour|snow|get worse)(?: soon)?",
        r"there is going to be (?:rain|a storm|a thunderstorm|bad weather)",
        r"(?:those|the) (?:dark )?clouds are going to (?:bring|cause) (?:rain|a storm|bad weather)",
        r"we are going to (?:have|get) (?:rain|a storm|bad weather)",
    )
    return _fullmatch_any(text, patterns)


def _match_q6(text: str) -> bool:
    if text in {_canonical(item) for item in _Q6}:
        return True
    patterns = (
        r"walking to the store,? i (?:got|had) my jacket soaked(?: by the rain)?",
        r"walking to the store,? i was (?:soaked by|caught in) the rain",
        r"(?:while|as|when) i was walking to the store,? the rain soaked my jacket",
        r"while walking to the store,? i (?:got|had) my jacket soaked(?: by the rain)?",
        r"the rain soaked my jacket (?:while|as|when) i was walking to the store",
        r"(?:while|as|when) i walked to the store,? my jacket was soaked by the rain",
    )
    return _fullmatch_any(text, patterns)


def _match_q9(text: str) -> bool:
    if text in {_canonical(item) for item in _Q9}:
        return True
    return _fullmatch_any(text, (
        r"(?:exercising|working out|doing exercise|getting exercise) (?:every|each) morning (?:is|can be) (?:healthy|beneficial|good for (?:you|your health))",
        r"(?:exercising|working out|doing exercise|getting exercise) in the morning (?:is|can be) (?:healthy|beneficial|good for (?:you|your health))",
    ))


_LOGICAL_RAIN_TERMS = frozenset({
    "cancel", "canceled", "cancelled", "delay", "delayed", "flood", "flooded", "game", "home",
    "indoors", "inside", "match", "outside", "picnic", "plans", "postpone", "postponed", "raincoat",
    "reschedule", "roads", "slippery", "stay", "streets", "take", "trip", "umbrella", "wear", "wet",
})


def _match_q11(text: str) -> bool:
    if text in {_canonical(item) for item in _Q11}:
        return True
    if not re.fullmatch(r"if it rains tomorrow,? .+", text):
        return False
    main_clause = re.sub(r"^if it rains tomorrow,?\s*", "", text)
    if not re.search(r"\bwill(?: not)?\b", main_clause):
        return False
    words = set(_WORD_RE.findall(main_clause))
    return bool(words & _LOGICAL_RAIN_TERMS)


RULES: dict[int, PlacementAnswerRule] = {
    1: PlacementAnswerRule(
        _Q1[0], _Q1,
        _exact_or_pattern(
            _Q1,
            r"the scientist's (?:careful )?analysis of the data(?: was (?:very careful|conducted with great care))?",
            r"the scientist (?:conducted|performed|carried out|completed|made) (?:(?:a )?(?:very )?careful analysis|an analysis) of the data(?: with great care)?",
            r"a careful analysis of the data was (?:conducted|performed|carried out|completed) by the scientist",
        ),
        "Requires the noun 'analysis' used correctly.",
    ),
    2: PlacementAnswerRule(
        _Q2[0], _Q2, _match_q2,
        "Checks an adjective immediately before 'birds', a migration verb, and a time expression. Underlining cannot be verified in plain text.",
    ),
    3: PlacementAnswerRule(
        _Q3[0], _Q3,
        _exact_or_pattern(
            _Q3,
            r"she walks to school every day",
            r"every day,? she walks to school",
        ),
    ),
    4: PlacementAnswerRule(
        _Q4[0], _Q4,
        _exact_or_pattern(
            _Q4,
            r"the train had(?: already)? left before we arrived at the station",
            r"by the time we arrived at the station,? the train had(?: already)? left",
            r"when we arrived at the station,? the train had already left",
            r"after the train had(?: already)? left,? we arrived at the station",
        ),
    ),
    5: PlacementAnswerRule(_Q5[0], _Q5, _match_q5),
    6: PlacementAnswerRule(_Q6[0], _Q6, _match_q6),
    7: PlacementAnswerRule(
        _Q7[0], _Q7,
        _exact_or_pattern(
            _Q7,
            r"although (?:the team|they) (?:had )?practiced hard,? (?:they|the team|it) lost the final",
            r"the team lost the final although (?:the team|they) (?:had )?practiced hard",
        ),
    ),
    8: PlacementAnswerRule(
        _Q8[0], _Q8,
        _exact_or_pattern(
            _Q8,
            r"she said(?: that)? she would (?:finish|complete) the project (?:the )?(?:next|following) day",
        ),
    ),
    9: PlacementAnswerRule(_Q9[0], _Q9, _match_q9),
    10: PlacementAnswerRule(
        _Q10[0], _Q10,
        _exact_or_pattern(
            _Q10,
            r"she (?:studies|works) (?:very )?(?:hard|diligently) (?:in order |so as )?to (?:pass|succeed in) (?:the|her) exam",
            r"(?:in order |so as )?to pass (?:the|her) exam,? she (?:studies|works) (?:very )?(?:hard|diligently)",
        ),
    ),
    11: PlacementAnswerRule(
        _Q11[0], _Q11, _match_q11,
        "Checks first-conditional form plus a reviewed weather-related consequence vocabulary.",
    ),
    12: PlacementAnswerRule(
        _Q12[0], _Q12,
        _exact_or_pattern(
            _Q12,
            r"if he had studied(?: harder)?,? he (?:would|might) not have failed the test",
            r"he (?:would|might) not have failed the test if he had studied(?: harder)?",
            r"had he studied(?: harder)?,? he (?:would|might) not have failed the test",
        ),
    ),
    13: PlacementAnswerRule(
        _Q13[0], _Q13,
        _exact_or_pattern(_Q13, r"have you", r"you have not finished your homework,? have you"),
    ),
    14: PlacementAnswerRule(
        _Q14[0], _Q14,
        _exact_or_pattern(
            _Q14,
            r"could you tell me where the train station is(?:,? please)?",
            r"could you please tell me where the train station is",
        ),
    ),
    15: PlacementAnswerRule(
        _Q15[0], _Q15,
        _exact_or_pattern(
            _Q15,
            r"the results will be announced(?: by the committee)? on friday",
            r"on friday,? the results will be announced(?: by the committee)?",
        ),
    ),
}


def _question_test_name(question) -> str:
    test_id = getattr(question, "test_id", None)
    if test_id:
        return str(test_id).strip()
    test = getattr(question, "test", None)
    return str(getattr(test, "name", "") or "").strip()


def is_placement_offline_open_question(question) -> bool:
    try:
        number = int(getattr(question, "number", 0) or 0)
    except (TypeError, ValueError):
        return False
    return _question_test_name(question).casefold() == PLACEMENT_OFFLINE_TEST_NAME.casefold() and number in RULES


def check_placement_offline_answer(question, response) -> bool | None:
    """Return None when the question is outside this special test, else a deterministic result."""
    if not is_placement_offline_open_question(question):
        return None
    text = _canonical(response)
    if not text:
        return False
    return RULES[int(question.number)].matcher(text)


def placement_offline_reference_answer(question) -> str | None:
    if not is_placement_offline_open_question(question):
        return None
    return RULES[int(question.number)].reference


def accepted_answers_text(number: int) -> str:
    return "\n".join(RULES[number].accepted)


def rule_summary(number: int) -> str:
    rule = RULES[number]
    return rule.note or f"{len(rule.accepted)} reviewed accepted variants plus deterministic full-sentence rules."
