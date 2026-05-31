"""Patient-facing token cap (prompt budget vs reasoning API max_tokens)."""

import pytest

from app.agents.reasoning import (
    P_MAX,
    build_reasoning_prompts,
    reset_llm_callers,
    run_reasoning,
    set_llm_callers,
)
from app.agents.voice_config import (
    patient_reasoning_max_tokens,
    patient_text_max_tokens,
    voice_patient_max_tokens,
    voice_reasoning_max_tokens,
)
from app.schemas import ClinicalContext, PatientProfile, SessionMeta, Turn
from tests.conftest import make_reasoning_json


@pytest.fixture(autouse=True)
def _reset_llm():
    reset_llm_callers()
    yield
    reset_llm_callers()


def test_p_max_defaults_to_150(monkeypatch):
    monkeypatch.delenv("PATIENT_RESPONSE_MAX_TOKENS", raising=False)
    from importlib import reload

    import app.agents.reasoning as reasoning_mod

    reload(reasoning_mod)
    assert reasoning_mod.P_MAX == 150


def test_patient_text_max_tokens_text_and_voice(monkeypatch):
    monkeypatch.setenv("PATIENT_RESPONSE_MAX_TOKENS", "150")
    monkeypatch.setenv("VOICE_PATIENT_RESPONSE_MAX_TOKENS", "150")
    assert patient_text_max_tokens("text") == 150
    assert patient_text_max_tokens("voice") == 150
    assert voice_patient_max_tokens() == 150


def test_build_reasoning_prompts_includes_patient_max_in_system(monkeypatch):
    monkeypatch.setenv("PATIENT_RESPONSE_MAX_TOKENS", "150")
    ctx = ClinicalContext(
        patient_profile=PatientProfile(),
        session_meta=SessionMeta(
            session_id="s-cap",
            channel="text",
            mode="triage",
            user_type="patient",
        ),
        rolling_summary="",
        recent_turns=[],
        current_input=Turn(sender="patient", text="hello"),
    )
    system, _user, max_tokens = build_reasoning_prompts(ctx, "triage")
    assert f"PATIENT RESPONSE MAX: {patient_text_max_tokens('text')} tokens" in system
    assert "REQUIRED" in system
    assert "source_reserve" not in system  # template var substituted
    assert "18" in system or "tokens for one inline cite" in system
    assert "complete sentences" in system.lower() or "complete sentence" in system.lower()
    assert "SCOPE" in system
    assert max_tokens == patient_reasoning_max_tokens("text")


@pytest.mark.asyncio
async def test_run_reasoning_passes_reasoning_max_not_patient_cap(monkeypatch):
    monkeypatch.setenv("PATIENT_RESPONSE_MAX_TOKENS", "150")
    captured = []

    async def capture_deepseek(_system, _user, max_tokens=900, **kwargs):
        captured.append((_system, max_tokens))
        return make_reasoning_json("Brief reply.")

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
    system, max_tokens = captured[0]
    assert f"PATIENT RESPONSE MAX: {patient_text_max_tokens('text')} tokens" in system
    assert max_tokens == patient_reasoning_max_tokens("text")
    assert max_tokens != patient_text_max_tokens("text")


@pytest.mark.asyncio
async def test_run_reasoning_voice_uses_voice_reasoning_max():
    captured = []

    async def capture_deepseek(_system, _user, max_tokens=900, **kwargs):
        captured.append(max_tokens)
        return make_reasoning_json("Voice.")

    set_llm_callers(deepseek_fn=capture_deepseek)

    ctx = ClinicalContext(
        patient_profile=PatientProfile(),
        session_meta=SessionMeta(
            session_id="s-v",
            channel="voice",
            mode="triage",
            user_type="patient",
        ),
        rolling_summary="",
        recent_turns=[],
        current_input=Turn(sender="patient", text="hello"),
    )

    await run_reasoning(ctx, "triage", "deepseek")
    assert captured[0] == voice_reasoning_max_tokens()


def test_custom_patient_max_via_env(monkeypatch):
    monkeypatch.setenv("PATIENT_RESPONSE_MAX_TOKENS", "99")
    # Re-import would be needed for P_MAX module load; build_reasoning_prompts reads channel helper
    assert patient_text_max_tokens("text") == 99
