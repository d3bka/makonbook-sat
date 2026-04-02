from typing import Dict

DEFAULT_BANDS = [
    {
        "name": "low",
        "min_ratio": 0.00,
        "max_ratio": 0.449999,
        "m2_weight": 0.36,
        "m2_multiplier": 0.92,
        "section_cap": 650,
        "curve_power": 1.02,
        "range_half": 20,
    },
    {
        "name": "mid",
        "min_ratio": 0.45,
        "max_ratio": 0.749999,
        "m2_weight": 0.42,
        "m2_multiplier": 1.00,
        "section_cap": 730,
        "curve_power": 0.97,
        "range_half": 20,
    },
    {
        "name": "high",
        "min_ratio": 0.75,
        "max_ratio": 1.00,
        "m2_weight": 0.48,
        "m2_multiplier": 1.05,
        "section_cap": 800,
        "curve_power": 0.92,
        "range_half": 10,
    },
]

SECTION_CONFIG = {
    "english": {
        "m1_total": 27,
        "m2_total": 27,
        "bands": DEFAULT_BANDS,
    },
    "math": {
        "m1_total": 22,
        "m2_total": 22,
        "bands": DEFAULT_BANDS,
    },
}

def _round_to_ten(value: float) -> int:
    return int(round(value / 10.0) * 10)

def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))

def _get_band(ratio: float, bands: list[dict]) -> dict:
    for band in bands:
        if band["min_ratio"] <= ratio <= band["max_ratio"]:
            return band
    return bands[-1]

def _build_range(score: int, cap: int, half_width: int) -> Dict[str, int]:
    return {
        "lower": max(200, score - half_width),
        "upper": min(cap, score + half_width),
    }

def _calculate_section_score(m1_correct: int, m2_correct: int, *, section_key: str) -> dict:
    config = SECTION_CONFIG[section_key]
    m1_total = config["m1_total"]
    m2_total = config["m2_total"]

    m1_ratio = _clamp(m1_correct / m1_total if m1_total else 0, 0.0, 1.0)
    m2_ratio = _clamp(m2_correct / m2_total if m2_total else 0, 0.0, 1.0)

    band = _get_band(m1_ratio, config["bands"])
    adjusted_m2_ratio = _clamp(m2_ratio * band["m2_multiplier"], 0.0, 1.0)

    m2_weight = band["m2_weight"]
    m1_weight = 1.0 - m2_weight
    combined_ratio = (m1_weight * m1_ratio) + (m2_weight * adjusted_m2_ratio)
    combined_ratio = _clamp(combined_ratio, 0.0, 1.0)

    raw_score = 200 + ((combined_ratio ** band["curve_power"]) * (band["section_cap"] - 200))
    score = _round_to_ten(raw_score)
    score = int(_clamp(score, 200, band["section_cap"]))

    return {
        "score": score,
        "range": _build_range(score, band["section_cap"], band["range_half"]),
        "band": band["name"],
        "m1_ratio": round(m1_ratio, 4),
        "m2_ratio": round(m2_ratio, 4),
        "combined_ratio": round(combined_ratio, 4),
        "cap": band["section_cap"],
    }

def get_english(m1, m2, _unused_total_questions=54):
    section = _calculate_section_score(m1, m2, section_key="english")
    return section["score"], section["range"]

def get_math(m1, m2, _unused_total_questions=44):
    section = _calculate_section_score(m1, m2, section_key="math")
    return section["score"], section["range"]

def get_total(e, a, l, u):
    english_section = _calculate_section_score(e, a, section_key="english")
    math_section = _calculate_section_score(l, u, section_key="math")
    total_score = english_section["score"] + math_section["score"]
    return {
        "total": total_score,
        "range_total": {
            "lower": english_section["range"]["lower"] + math_section["range"]["lower"],
            "upper": english_section["range"]["upper"] + math_section["range"]["upper"],
        },
        "sections": {
            "english": english_section,
            "math": math_section,
        },
    }

