from __future__ import annotations

import re
import unicodedata


_TRANSLATION = str.maketrans({
    "’": "'", "‘": "'", "“": '"', "”": '"',
    "–": "-", "—": "-", "−": "-", "…": "...",
    "\u00a0": " ",
})


def normalize_text_answer(value) -> str:
    """Normalize harmless typography without changing the student's meaning."""
    if value is None:
        return ""
    text = unicodedata.normalize("NFKC", str(value)).translate(_TRANSLATION)
    text = re.sub(r"\s+", " ", text).strip().casefold()
    text = re.sub(r"\s+([,;:!?])", r"\1", text)
    text = re.sub(r"[.!?]+$", "", text).strip()
    return text
