"""Voice channel prompt payload and context assembly."""

import pytest

from app.agents.reasoning import (
    VOICE_CHANNEL_USER_NOTE,
    reset_llm_callers,
    run_reasoning,
    set_llm_callers,
)
from app.agents.voice_config import voice_reasoning_max_tokens
from app.agents.session import create_session, load_context
from app.schemas import ClinicalContext, PatientProfile, SessionMeta, Turn
from tests.conftest import make_reasoning_json


@pytest.fixture(autouse=True)
def _reset_llm():
    reset_llm_callers()
    yield
    reset_llm_callers()


@pytest.mark.asyncio
async def test_load_context_prefers_turn_channel(db_session):
    sid = await create_session(db_session, "patient-voice", channel="text")
    ctx = await load_context(db_session, sid, "hello", turn_channel="voice")
    assert ctx.session_meta.channel == "voice"


@pytest.mark.asyncio
async def test_run_reasoning_appends_voice_note_for_voice_channel():
    captured = []

    async def capture_deepseek(_system, user, max_tokens=900, **kwargs):
        captured.append((user, max_tokens))
        return make_reasoning_json("Voice-optimized reply.")

    set_llm_callers(deepseek_fn=capture_deepseek)

    ctx = ClinicalContext(
        patient_profile=PatientProfile(),
        session_meta=SessionMeta(
            session_id="s-voice",
            channel="voice",
            mode="triage",
            user_type="patient",
        ),
        rolling_summary="",
        recent_turns=[],
        current_input=Turn(sender="patient", text="headache"),
    )

    await run_reasoning(ctx, "triage", "deepseek")
    assert len(captured) == 1
    user_payload, max_tokens = captured[0]
    assert VOICE_CHANNEL_USER_NOTE in user_payload
    assert "3 short sentences" in VOICE_CHANNEL_USER_NOTE
    assert '"channel":"voice"' in user_payload or '"channel": "voice"' in user_payload
    assert max_tokens == voice_reasoning_max_tokens()


@pytest.mark.asyncio
async def test_run_reasoning_omits_voice_note_for_text_channel():
    captured = []

    async def capture_deepseek(_system, user, max_tokens=900, **kwargs):
        captured.append(max_tokens)
        return make_reasoning_json("Text reply.")

    set_llm_callers(deepseek_fn=capture_deepseek)

    ctx = ClinicalContext(
        patient_profile=PatientProfile(),
        session_meta=SessionMeta(
            session_id="s-text",
            channel="text",
            mode="triage",
            user_type="patient",
        ),
        rolling_summary="",
        recent_turns=[],
        current_input=Turn(sender="patient", text="hello"),
    )

    await run_reasoning(ctx, "triage", "deepseek")
    assert captured[0] == 900
