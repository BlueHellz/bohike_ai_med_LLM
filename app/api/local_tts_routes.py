"""Local dev-only Piper TTS routes (gated by LOCAL_TTS_ENABLED)."""

import os

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from local_tts import LocalTtsError, default_voice_id, list_voices, synthesize
from local_tts.speech_text import prepare_text_for_speech

router = APIRouter(prefix="/local-tts", tags=["local-tts"])


def local_tts_enabled() -> bool:
    return os.getenv("LOCAL_TTS_ENABLED", "").strip().lower() in ("1", "true", "yes")


class LocalTtsSpeakRequest(BaseModel):
    text: str = Field(..., min_length=1)
    voice_id: str | None = None


@router.get("/voices")
async def get_voices():
    if not local_tts_enabled():
        raise HTTPException(
            status_code=503,
            detail="Local TTS is disabled. Set LOCAL_TTS_ENABLED=true in .env and restart.",
        )
    return {
        "default_voice_id": default_voice_id(),
        "voices": list_voices(),
    }


@router.post("/speak")
async def speak(body: LocalTtsSpeakRequest):
    if not local_tts_enabled():
        raise HTTPException(
            status_code=503,
            detail="Local TTS is disabled. Set LOCAL_TTS_ENABLED=true in .env and restart.",
        )
    voice_id = body.voice_id or default_voice_id()
    spoken = prepare_text_for_speech(body.text)
    if not spoken:
        raise HTTPException(status_code=400, detail="No speakable text after preparing input")
    try:
        wav = synthesize(spoken, voice_id=voice_id)
    except LocalTtsError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return Response(content=wav, media_type="audio/wav")
