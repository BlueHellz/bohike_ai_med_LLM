"""Synthesize WAV audio with Kokoro-82M via kokoro-onnx (optional dev TTS)."""

from __future__ import annotations

import io
import json
import os
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_VOICES_CATALOG = Path(__file__).with_name("kokoro_voices.json")
_DEFAULT_MODEL_DIR = _REPO_ROOT / "voices" / "kokoro"
_MODEL_FILE = "kokoro-v1.0.onnx"
_VOICES_BIN = "voices-v1.0.bin"

_kokoro_instance = None
_catalog: dict | None = None


class KokoroTtsError(Exception):
    """Raised when Kokoro TTS cannot run (missing deps, models, or bad input)."""


def kokoro_tts_enabled() -> bool:
    return os.getenv("KOKORO_TTS_ENABLED", "").strip().lower() in ("1", "true", "yes")


def model_dir() -> Path:
    raw = (os.getenv("KOKORO_TTS_MODEL_DIR") or "").strip()
    return Path(raw) if raw else _DEFAULT_MODEL_DIR


def model_paths() -> tuple[Path, Path]:
    base = model_dir()
    return base / _MODEL_FILE, base / _VOICES_BIN


def models_ready() -> bool:
    onnx_path, voices_path = model_paths()
    return onnx_path.is_file() and voices_path.is_file()


def _load_catalog() -> dict:
    global _catalog
    if _catalog is None:
        _catalog = json.loads(_VOICES_CATALOG.read_text(encoding="utf-8"))
    return _catalog


def default_voice_id() -> str:
    return _load_catalog()["default_voice_id"]


def list_voices() -> list[dict]:
    ready = models_ready()
    out: list[dict] = []
    for v in _load_catalog()["voices"]:
        out.append({**v, "ready": ready})
    return out


def _setup_hint() -> str:
    return (
        "Run ./scripts/setup_kokoro_tts.sh (downloads ~325 MB model assets) "
        "and pip install -r local_tts/kokoro_requirements.txt"
    )


def _get_kokoro():
    global _kokoro_instance
    if _kokoro_instance is not None:
        return _kokoro_instance

    try:
        from kokoro_onnx import Kokoro
    except ImportError as exc:
        raise KokoroTtsError(
            f"kokoro-onnx is not installed. {_setup_hint()}"
        ) from exc

    onnx_path, voices_path = model_paths()
    if not models_ready():
        raise KokoroTtsError(f"Kokoro model files missing under {model_dir()}. {_setup_hint()}")

    _kokoro_instance = Kokoro(str(onnx_path), str(voices_path))
    return _kokoro_instance


def synthesize(text: str, voice_id: str | None = None, speed: float | None = None) -> bytes:
    """Synthesize ``text`` to WAV bytes using Kokoro-82M."""
    spoken = (text or "").strip()
    if not spoken:
        raise KokoroTtsError("Text is empty")

    voice = voice_id or default_voice_id()
    known = {v["id"] for v in _load_catalog()["voices"]}
    if voice not in known:
        raise KokoroTtsError(f"Unknown Kokoro voice_id: {voice}")

    spd = speed if speed is not None else float(os.getenv("KOKORO_TTS_SPEED", "1.0"))
    lang = (os.getenv("KOKORO_TTS_LANG") or "en-us").strip() or "en-us"

    try:
        import soundfile as sf
    except ImportError as exc:
        raise KokoroTtsError(
            "soundfile is not installed. pip install -r local_tts/kokoro_requirements.txt"
        ) from exc

    kokoro = _get_kokoro()
    try:
        samples, sample_rate = kokoro.create(spoken, voice=voice, speed=spd, lang=lang)
    except Exception as exc:
        raise KokoroTtsError(f"Kokoro synthesis failed: {exc}") from exc

    buf = io.BytesIO()
    sf.write(buf, samples, sample_rate, format="WAV")
    return buf.getvalue()
