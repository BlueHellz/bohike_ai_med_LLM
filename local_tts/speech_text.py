"""Prepare patient-facing text for local Piper playback."""

from __future__ import annotations

import re

_DISCLAIMER_STARTS = (
    "This information is not a substitute",
    "If you believe this is a medical emergency",
)

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


def prepare_text_for_speech(text: str, max_sentences: int = 6, max_chars: int = 600) -> str:
    """
    Strip legal disclaimers and long reference blocks before TTS.

    Disclaimers remain visible in the chat; they are omitted from spoken audio only.
    """
    cleaned = (text or "").strip()
    if not cleaned:
        return ""

    for marker in _DISCLAIMER_STARTS:
        idx = cleaned.find(marker)
        if idx != -1:
            cleaned = cleaned[:idx].strip()

    ref_idx = cleaned.find("References:")
    if ref_idx != -1:
        cleaned = cleaned[:ref_idx].strip()

    parts = [p.strip() for p in _SENTENCE_SPLIT.split(cleaned) if p.strip()]
    if not parts:
        return cleaned[:max_chars]

    limited = " ".join(parts[:max_sentences])
    if len(limited) > max_chars:
        limited = limited[:max_chars].rsplit(" ", 1)[0] + "."
    # Normalize spacing so Piper can insert pauses at punctuation boundaries.
    limited = re.sub(r"\s+", " ", limited)
    limited = re.sub(r"([,;])\s*", r"\1 ", limited)
    return limited.strip()
