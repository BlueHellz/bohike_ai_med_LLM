"""Tests for DeepSeek-only LLM provider configuration."""

import pytest
from httpx import ASGITransport, AsyncClient

from app.agents.reasoning import is_claude_enabled, reset_llm_callers, run_reasoning, set_llm_callers
from app.main import app
from app.schemas import ClinicalContext, PatientProfile, SessionMeta, Turn
from tests.conftest import make_reasoning_json


@pytest.fixture(autouse=True)
def _reset_llm():
    reset_llm_callers()
    yield
    reset_llm_callers()


@pytest.fixture
async def client():
    from app.database import init_db

    await init_db()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


def test_is_claude_disabled_when_llm_provider_deepseek(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "deepseek")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-should-not-enable")
    assert is_claude_enabled() is False


@pytest.mark.asyncio
async def test_malformed_json_retries_deepseek_not_claude(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "deepseek")
    calls = {"deepseek": 0, "claude": 0}

    async def counting_deepseek(_s, _u, max_tokens=900):
        calls["deepseek"] += 1
        return "not valid json"

    async def counting_claude(_s, _u, max_tokens=900):
        calls["claude"] += 1
        return make_reasoning_json("should not be used")

    set_llm_callers(deepseek_fn=counting_deepseek, claude_fn=counting_claude)

    ctx = ClinicalContext(
        patient_profile=PatientProfile(),
        session_meta=SessionMeta(
            session_id="s1",
            channel="text",
            mode="triage",
            user_type="patient",
        ),
        rolling_summary="",
        recent_turns=[],
        current_input=Turn(sender="patient", text="hello"),
    )

    raw, used_claude = await run_reasoning(ctx, "triage", "deepseek")
    assert calls["deepseek"] == 2
    assert calls["claude"] == 0
    assert used_claude is False
    assert raw == "not valid json"


@pytest.mark.asyncio
async def test_surgeon_returns_501_when_claude_disabled(client, monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "deepseek")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    r = await client.post(
        "/api/v1/surgeon/pre-op",
        json={
            "surgeon_id": "doc1",
            "surgical_context": {
                "procedure_type": "laparoscopic_cholecystectomy",
                "phase": "pre_op",
                "patient_profile": {},
            },
            "query": "Pre-op briefing please",
        },
    )
    assert r.status_code == 501
    assert "ANTHROPIC_API_KEY" in r.json()["detail"]


@pytest.mark.asyncio
async def test_mock_patient_profile_via_api(client):
    r = await client.get("/api/v1/patients/mock-patient-002/profile")
    assert r.status_code == 200
    data = r.json()
    assert data["age"] == 34
    assert "asthma" in data["known_conditions_summary"].lower()


@pytest.mark.asyncio
async def test_put_profile_overrides_mock_fixture(client):
    await client.put(
        "/api/v1/patients/mock-patient-001/profile",
        json={"age": 99, "known_conditions_summary": "Override condition"},
    )
    r = await client.get("/api/v1/patients/mock-patient-001/profile")
    assert r.json()["age"] == 99
    assert r.json()["known_conditions_summary"] == "Override condition"
