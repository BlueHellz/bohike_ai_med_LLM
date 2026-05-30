"""
Voice channel integration contract.

The backend accepts transcribed text only. Speech-to-text and text-to-speech run
entirely on the client device. See ``docs/VOICE_PIPELINE.md`` for the full sequence.
"""

from typing import Literal

Channel = Literal["text", "voice"]


def normalize_voice_turn(text: str, channel: str = "voice") -> tuple[str, Channel]:
    """
    Normalize inbound turn payload for the shared text reasoning pipeline.

    Voice and text channels share identical clinical processing; the channel value
    is persisted on ``SessionMessage`` records for analytics and audit.
    """
    normalized_channel: Channel = "voice" if channel == "voice" else "text"
    return text.strip(), normalized_channel


def voice_turn_metadata(channel: str) -> dict[str, str]:
    """Return metadata tags attached to voice-channel session messages."""
    if channel == "voice":
        return {"input_modality": "voice", "stt": "client-side", "tts": "client-side"}
    return {"input_modality": "text"}
