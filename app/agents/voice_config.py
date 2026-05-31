"""Patient consultation latency settings (text and voice)."""

import os


def _env_true(name: str, default: str = "true") -> bool:
    return os.getenv(name, default).strip().lower() in ("1", "true", "yes")


def patient_defer_summary_enabled() -> bool:
    """
    When enabled, rolling summary runs in the background after the HTTP response.

    Removes the second blocking DeepSeek call from the patient-facing latency path.
    """
    if _env_true("PATIENT_DEFER_SUMMARY", "true"):
        return True
    return _env_true("VOICE_SKIP_SUMMARY", "true")


def should_defer_summary(channel: str) -> bool:
    return patient_defer_summary_enabled()


def patient_reasoning_max_tokens(channel: str) -> int:
    if channel == "voice":
        return int(os.getenv("VOICE_REASONING_MAX_TOKENS", "550"))
    return int(os.getenv("PATIENT_REASONING_MAX_TOKENS", "550"))


def voice_reasoning_max_tokens() -> int:
    return patient_reasoning_max_tokens("voice")


def patient_text_max_tokens(channel: str) -> int:
    """Token budget for patient_response_text (prompt + post-validation), not full JSON."""
    if channel == "voice":
        return voice_patient_max_tokens()
    return int(os.getenv("PATIENT_RESPONSE_MAX_TOKENS", "150"))


def voice_patient_max_tokens() -> int:
    return int(os.getenv("VOICE_PATIENT_RESPONSE_MAX_TOKENS", "150"))
