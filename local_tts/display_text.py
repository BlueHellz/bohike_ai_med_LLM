"""Split patient-facing text into clinical body and legal disclaimers."""

from __future__ import annotations

from app.agents.safety import EMERGENCY_DISCLAIMER, STANDARD_DISCLAIMER

DISCLAIMER_MARKERS = (STANDARD_DISCLAIMER, EMERGENCY_DISCLAIMER)


def split_patient_display_text(text: str) -> tuple[str, str | None, str | None]:
    """
    Return (clinical_body, emergency_disclaimer, standard_disclaimer).

    Disclaimers are removed from the body and returned separately for display.
    """
    cleaned = (text or "").strip()
    emergency: str | None = None
    standard: str | None = None

    if cleaned.startswith(EMERGENCY_DISCLAIMER):
        emergency = EMERGENCY_DISCLAIMER
        cleaned = cleaned[len(EMERGENCY_DISCLAIMER) :].lstrip("\n").strip()

    if STANDARD_DISCLAIMER in cleaned:
        idx = cleaned.find(STANDARD_DISCLAIMER)
        standard = STANDARD_DISCLAIMER
        cleaned = cleaned[:idx].rstrip()

    return cleaned, emergency, standard
