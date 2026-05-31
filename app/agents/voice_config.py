"""Voice channel latency and summary deferral settings."""

import os


def voice_skip_summary_enabled() -> bool:
    """When enabled, voice turns return before the rolling-summary LLM call completes."""
    return os.getenv("VOICE_SKIP_SUMMARY", "true").strip().lower() in ("1", "true", "yes")


def should_defer_summary(channel: str) -> bool:
    return channel == "voice" and voice_skip_summary_enabled()


def voice_reasoning_max_tokens() -> int:
    return int(os.getenv("VOICE_REASONING_MAX_TOKENS", "650"))


def voice_patient_max_tokens() -> int:
    return int(os.getenv("VOICE_PATIENT_RESPONSE_MAX_TOKENS", "120"))
