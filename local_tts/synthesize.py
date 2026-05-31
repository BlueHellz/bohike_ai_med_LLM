"""Synthesize WAV audio with local Piper ONNX models."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from functools import lru_cache
from pathlib import Path
from typing import Any

_MODULE_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _MODULE_DIR.parent
_VOICES_JSON = _MODULE_DIR / "voices.json"
_DEFAULT_VOICES_DIR = _REPO_ROOT / "voices" / "piper"
_DEFAULT_PIPER_DIR = _REPO_ROOT / "tools" / "piper"
_PIPER_BIN = _DEFAULT_PIPER_DIR / "piper"


def _setup_help() -> str:
    return (
        "Install one of:\n"
        "  A) Python 3.12 from https://www.python.org/downloads/macos/ "
        "(pip does not install Python), then: python3.12 -m venv .venv312 && "
        "source .venv312/bin/activate && pip install -r local_tts/requirements.txt "
        '&& pip install --no-deps "piper-tts>=1.2.0"\n'
        "  B) Piper CLI + voice models: ./scripts/setup_local_tts.sh"
    )


def piper_cli_dir() -> Path:
    raw = (os.getenv("LOCAL_TTS_PIPER_DIR") or "").strip()
    return Path(raw) if raw else _DEFAULT_PIPER_DIR




class LocalTtsError(Exception):
    """Raised when local TTS cannot run (missing deps, voice files, or bad input)."""


def voices_dir() -> Path:
    raw = (os.getenv("LOCAL_TTS_VOICES_DIR") or "").strip()
    return Path(raw) if raw else _DEFAULT_VOICES_DIR


def piper_binary() -> Path | None:
    """Return the Piper CLI executable when present."""
    override = (os.getenv("LOCAL_TTS_PIPER_BIN") or "").strip()
    if override:
        path = Path(override)
        return path if path.is_file() and os.access(path, os.X_OK) else None
    if _PIPER_BIN.is_file() and os.access(_PIPER_BIN, os.X_OK):
        return _PIPER_BIN
    legacy = piper_cli_dir() / "piper" / "piper"
    if legacy.is_file() and os.access(legacy, os.X_OK):
        return legacy
    return None


@lru_cache(maxsize=1)
def _load_catalog() -> dict[str, Any]:
    if not _VOICES_JSON.is_file():
        raise LocalTtsError(f"Voice catalog missing: {_VOICES_JSON}")
    with _VOICES_JSON.open(encoding="utf-8") as f:
        return json.load(f)


def default_voice_id() -> str:
    catalog = _load_catalog()
    return str(catalog.get("default_voice_id") or "en_US-lessac-medium")


def _voice_entry(voice_id: str) -> dict[str, Any]:
    catalog = _load_catalog()
    for entry in catalog.get("voices", []):
        if entry.get("id") == voice_id:
            return entry
    raise LocalTtsError(f"Unknown voice_id: {voice_id}")


def voice_model_paths(voice_id: str) -> tuple[Path, Path]:
    entry = _voice_entry(voice_id)
    model_file = entry.get("model_file") or f"{voice_id}.onnx"
    base = voices_dir()
    onnx_path = base / model_file
    config_path = base / f"{model_file}.json"
    return onnx_path, config_path


def _ensure_voice_files(voice_id: str) -> tuple[Path, Path]:
    onnx_path, config_path = voice_model_paths(voice_id)
    if not onnx_path.is_file():
        raise LocalTtsError(
            f"Voice model not found: {onnx_path}. "
            "Run: ./scripts/setup_local_tts.sh"
        )
    if not config_path.is_file():
        raise LocalTtsError(
            f"Voice config not found: {config_path}. "
            "Run: ./scripts/setup_local_tts.sh"
        )
    return onnx_path, config_path


def list_voices() -> list[dict[str, Any]]:
    """Return catalog entries with a ``ready`` flag when model files exist."""
    out: list[dict[str, Any]] = []
    for entry in _load_catalog().get("voices", []):
        vid = entry["id"]
        onnx_path, config_path = voice_model_paths(vid)
        ready = onnx_path.is_file() and config_path.is_file()
        out.append(
            {
                "id": vid,
                "name": entry.get("name", vid),
                "language": entry.get("language", "en-US"),
                "quality": entry.get("quality"),
                "description": entry.get("description", ""),
                "ready": ready,
            }
        )
    return out


def _piper_subprocess_env(work_dir: Path) -> dict[str, str]:
    env = os.environ.copy()
    lib_dir = work_dir / "lib"
    if lib_dir.is_dir():
        prev = env.get("DYLD_LIBRARY_PATH", "")
        env["DYLD_LIBRARY_PATH"] = (
            f"{lib_dir}{os.pathsep}{prev}" if prev else str(lib_dir)
        )
    return env


def _piper_float_env(name: str, default: float) -> float:
    raw = (os.getenv(name) or str(default)).strip()
    try:
        return float(raw)
    except ValueError:
        return default


def _piper_prosody_args() -> list[str]:
    """
    Piper prosody tuned for conversational speech.

    length_scale > 1.0 yields slower, more natural cadence.
    sentence_silence adds pause between sentences within one synthesis pass.
    """
    return [
        "--length_scale",
        str(_piper_float_env("LOCAL_TTS_LENGTH_SCALE", 1.12)),
        "--noise_scale",
        str(_piper_float_env("LOCAL_TTS_NOISE_SCALE", 0.667)),
        "--noise_w",
        str(_piper_float_env("LOCAL_TTS_NOISE_W", 0.78)),
        "--sentence_silence",
        str(_piper_float_env("LOCAL_TTS_SENTENCE_SILENCE", 0.42)),
    ]


def _synthesize_via_binary(text: str, voice_id: str) -> bytes:
    binary = piper_binary()
    if binary is None:
        raise LocalTtsError(_setup_help())

    onnx_path, config_path = _ensure_voice_files(voice_id)
    work_dir = binary.parent

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        out_path = Path(tmp.name)

    try:
        proc = subprocess.run(
            [
                str(binary),
                "--model",
                str(onnx_path.resolve()),
                "--config",
                str(config_path.resolve()),
                *_piper_prosody_args(),
                "--output_file",
                str(out_path),
            ],
            input=text,
            capture_output=True,
            cwd=str(work_dir),
            text=True,
            timeout=120,
            check=False,
            env=_piper_subprocess_env(work_dir),
        )
        if proc.returncode != 0:
            detail = (proc.stderr or proc.stdout or "").strip()
            raise LocalTtsError(
                f"Piper binary failed (exit {proc.returncode})"
                + (f": {detail}" if detail else "")
            )
        if not out_path.is_file() or out_path.stat().st_size == 0:
            raise LocalTtsError("Piper binary produced no audio output")
        return out_path.read_bytes()
    except OSError as exc:
        raise LocalTtsError(f"Failed to run Piper binary: {exc}") from exc
    finally:
        out_path.unlink(missing_ok=True)


@lru_cache(maxsize=8)
def _load_voice(voice_id: str):
    try:
        from piper.voice import PiperVoice
    except ImportError as exc:
        msg = str(exc)
        if "onnxruntime" in msg:
            raise LocalTtsError(
                "onnxruntime is not installed for this Python version. "
                "Run ./scripts/setup_local_tts.sh (Piper binary, no extra packages), "
                "or install Python 3.12 from https://www.python.org/downloads/macos/ "
                "and pip install -r local_tts/requirements.txt"
            ) from exc
        raise LocalTtsError(
            "piper-tts is not installed. Run ./scripts/setup_local_tts.sh, "
            "or: pip install -r local_tts/requirements.txt"
        ) from exc

    onnx_path, config_path = _ensure_voice_files(voice_id)
    return PiperVoice.load(str(onnx_path), config_path=str(config_path))


def _synthesize_via_python(text: str, voice_id: str) -> bytes:
    voice = _load_voice(voice_id)
    return voice.synthesize(text)


def synthesize(text: str, voice_id: str | None = None) -> bytes:
    """
    Synthesize ``text`` to WAV bytes using a local Piper model.

    Tries the bundled ``tools/piper/piper`` CLI first (no onnxruntime needed),
    then falls back to the piper-tts Python package when available.
    No network calls are made at synthesis time.
    """
    cleaned = (text or "").strip()
    if not cleaned:
        raise LocalTtsError("text is empty")

    vid = voice_id or default_voice_id()
    _ensure_voice_files(vid)

    if piper_binary() is not None:
        return _synthesize_via_binary(cleaned, vid)

    return _synthesize_via_python(cleaned, vid)
