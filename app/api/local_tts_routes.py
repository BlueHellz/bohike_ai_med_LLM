"""Local dev-only TTS routes (Piper and optional Kokoro; gated by env)."""

import os

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field

from local_tts import LocalTtsError, default_voice_id, list_voices, synthesize as piper_synthesize
from local_tts.kokoro_synthesize import (
    KokoroTtsError,
    default_voice_id as kokoro_default_voice_id,
    kokoro_tts_enabled,
    list_voices as list_kokoro_voices,
    models_ready as kokoro_models_ready,
    synthesize as kokoro_synthesize,
)
from local_tts.speech_text import prepare_text_for_speech

router = APIRouter(prefix="/local-tts", tags=["local-tts"])

_VALID_ENGINES = frozenset({"piper", "kokoro"})


def local_tts_enabled() -> bool:
    return os.getenv("LOCAL_TTS_ENABLED", "").strip().lower() in ("1", "true", "yes")


def default_engine() -> str:
    raw = (os.getenv("LOCAL_TTS_DEFAULT_ENGINE") or "piper").strip().lower()
    if raw == "kokoro" and kokoro_tts_enabled():
        return "kokoro"
    if local_tts_enabled():
        return "piper"
    if kokoro_tts_enabled():
        return "kokoro"
    return raw if raw in _VALID_ENGINES else "piper"


class LocalTtsSpeakRequest(BaseModel):
    text: str = Field(..., min_length=1)
    voice_id: str | None = None
    engine: str | None = None


def _engine_enabled(engine: str) -> bool:
    if engine == "piper":
        return local_tts_enabled()
    if engine == "kokoro":
        return kokoro_tts_enabled()
    return False


def _resolve_engine(requested: str | None) -> str:
    engine = (requested or default_engine()).strip().lower()
    if engine not in _VALID_ENGINES:
        raise HTTPException(status_code=400, detail=f"Unknown TTS engine: {engine}")
    return engine


@router.get("/engines")
async def get_engines():
    piper_on = local_tts_enabled()
    kokoro_on = kokoro_tts_enabled()
    if not piper_on and not kokoro_on:
        raise HTTPException(
            status_code=503,
            detail=(
                "Local TTS is disabled. Set LOCAL_TTS_ENABLED=true and/or "
                "KOKORO_TTS_ENABLED=true in .env and restart."
            ),
        )
    engines = []
    if piper_on:
        engines.append(
            {
                "id": "piper",
                "label": "Piper ONNX",
                "ready": any(v.get("ready") for v in list_voices()),
            }
        )
    if kokoro_on:
        engines.append(
            {
                "id": "kokoro",
                "label": "Kokoro-82M",
                "ready": kokoro_models_ready(),
            }
        )
    return {"default_engine": default_engine(), "engines": engines}


@router.get("/voices")
async def get_voices(engine: str = Query(default="piper")):
    engine = _resolve_engine(engine)
    if not _engine_enabled(engine):
        flag = "LOCAL_TTS_ENABLED" if engine == "piper" else "KOKORO_TTS_ENABLED"
        raise HTTPException(
            status_code=503,
            detail=f"{engine.capitalize()} TTS is disabled. Set {flag}=true in .env and restart.",
        )
    if engine == "kokoro":
        return {
            "engine": "kokoro",
            "default_voice_id": kokoro_default_voice_id(),
            "voices": list_kokoro_voices(),
        }
    return {
        "engine": "piper",
        "default_voice_id": default_voice_id(),
        "voices": list_voices(),
    }


@router.post("/speak")
async def speak(body: LocalTtsSpeakRequest):
    engine = _resolve_engine(body.engine)
    if not _engine_enabled(engine):
        flag = "LOCAL_TTS_ENABLED" if engine == "piper" else "KOKORO_TTS_ENABLED"
        raise HTTPException(
            status_code=503,
            detail=f"{engine.capitalize()} TTS is disabled. Set {flag}=true in .env and restart.",
        )

    spoken = prepare_text_for_speech(body.text)
    if not spoken:
        raise HTTPException(status_code=400, detail="No speakable text after preparing input")

    voice_id = body.voice_id
    try:
        if engine == "kokoro":
            wav = kokoro_synthesize(spoken, voice_id=voice_id)
        else:
            wav = piper_synthesize(spoken, voice_id=voice_id or default_voice_id())
    except (LocalTtsError, KokoroTtsError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return Response(content=wav, media_type="audio/wav")


@router.post("/kokoro/speak")
async def speak_kokoro(body: LocalTtsSpeakRequest):
    """Alias for Kokoro synthesis (same as POST /speak with engine=kokoro)."""
    body.engine = "kokoro"
    return await speak(body)
