"""Integration tests for consultation API endpoints and LLM wiring."""

import json
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.agents.reasoning import reset_llm_callers, set_llm_callers
from app.agents.safety import EMERGENCY_DISCLAIMER
from app.main import app
from tests.conftest import make_reasoning_json


@pytest.fixture(autouse=True)
def _reset_llm():
    reset_llm_callers()
    yield
    reset_llm_callers()


def _education_response():
    return make_reasoning_json(
        "Hypertension is high blood pressure. It develops over time due to genetics and lifestyle.",
        risk_flags=[],
        should_escalate=False,
        requires_review=False,
    )


def _chest_pain_response():
    return make_reasoning_json(
        "These symptoms need emergency evaluation right now.",
        risk_flags=[{"type": "chest_pain", "severity": "high", "rationale": "possible ACS"}],
        should_escalate=True,
        requires_review=True,
    )


def _headache_response():
    return make_reasoning_json(
        "I want to understand your headache better. When did it start, "
        "how severe is it on a scale of 1-10, and where is the pain located?",
    )


@pytest.fixture
async def client():
    from app.database import init_db

    await init_db()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_health(client):
    r = await client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["service"] == "aegis-medical-consultation-engine"
    assert "deepseek_configured" in body
    assert isinstance(body["deepseek_configured"], bool)


@pytest.mark.asyncio
async def test_citations_returned_in_turn_response(client):
    async def mock_deepseek(_s, _u, max_tokens=900, **kwargs):
        return make_reasoning_json(
            "Hypertension is elevated blood pressure (Source: CDC — hypertension basics). "
            "When did you last have it checked?",
            source_citations=["CDC — hypertension basics"],
        )

    set_llm_callers(deepseek_fn=mock_deepseek, claude_fn=mock_deepseek)

    r = await client.post(
        "/api/v1/sessions",
        json={"patient_id": "p-cite", "channel": "text", "citation_depth": "simple"},
    )
    sid = r.json()["session_id"]

    with patch("app.api.routes.call_deepseek", new=mock_deepseek):
        r = await client.post(
            f"/api/v1/sessions/{sid}/messages",
            json={
                "session_id": sid,
                "user_id": "p-cite",
                "text": "What is hypertension?",
            },
        )
    assert r.status_code == 200
    body = r.json()
    assert body["citations"] == ["CDC — hypertension basics"]
    assert "CDC — hypertension basics" in body["patient_response_text"]


@pytest.mark.asyncio
async def test_turn_no_clinician_layer_in_response(client):
    async def mock_deepseek(_s, _u, max_tokens=900, **kwargs):
        return _education_response()

    set_llm_callers(deepseek_fn=mock_deepseek, claude_fn=mock_deepseek)

    r = await client.post("/api/v1/sessions", json={"patient_id": "p1", "channel": "text"})
    sid = r.json()["session_id"]

    with patch("app.api.routes.call_deepseek", new=mock_deepseek):
        r = await client.post(
            f"/api/v1/sessions/{sid}/messages",
            json={
                "session_id": sid,
                "user_id": "p1",
                "text": "What is hypertension?",
            },
        )
    assert r.status_code == 200
    body = r.json()
    assert "clinician_layer" not in body
    assert "patient_response_text" in body
    assert body["session_id"] == sid


@pytest.mark.asyncio
async def test_emergency_creates_alert(client, db_session):
    async def mock_deepseek(_s, _u, max_tokens=900, **kwargs):
        return _chest_pain_response()

    set_llm_callers(deepseek_fn=mock_deepseek, claude_fn=mock_deepseek)

    r = await client.post("/api/v1/sessions", json={"patient_id": "p2", "channel": "text"})
    sid = r.json()["session_id"]

    with patch("app.api.routes.call_deepseek", new=mock_deepseek):
        r = await client.post(
            f"/api/v1/sessions/{sid}/messages",
            json={
                "session_id": sid,
                "user_id": "p2",
                "text": "I have crushing chest pain going to my left arm",
            },
        )
    assert r.status_code == 200
    body = r.json()
    assert body["patient_response_text"].startswith(EMERGENCY_DISCLAIMER)
    assert body["ui_hints"].get("show_emergency_banner") is True

    alerts = await client.get("/api/v1/physician/alerts")
    assert alerts.status_code == 200
    assert len(alerts.json()) >= 1


@pytest.mark.asyncio
async def test_malformed_llm_returns_safe_fallback(client):
    async def bad_deepseek(_s, _u, max_tokens=900, **kwargs):
        return "not valid json"

    set_llm_callers(deepseek_fn=bad_deepseek, claude_fn=bad_deepseek)

    r = await client.post("/api/v1/sessions", json={"patient_id": "p3", "channel": "text"})
    sid = r.json()["session_id"]

    with patch("app.api.routes.call_deepseek", side_effect=bad_deepseek):
        r = await client.post(
            f"/api/v1/sessions/{sid}/messages",
            json={
                "session_id": sid,
                "user_id": "p3",
                "text": "Hello",
            },
        )
    assert r.status_code == 200
    assert "difficulty processing" in r.json()["patient_response_text"].lower()


@pytest.mark.asyncio
async def test_physician_override_stored(client):
    async def mock_deepseek(_s, _u, max_tokens=900, **kwargs):
        return _headache_response()

    set_llm_callers(deepseek_fn=mock_deepseek, claude_fn=mock_deepseek)

    r = await client.post("/api/v1/sessions", json={"patient_id": "p4", "channel": "text"})
    sid = r.json()["session_id"]

    ov = await client.post(
        f"/api/v1/physician/session/{sid}/override",
        json={"text": "Patient's ECG shows ST elevation"},
    )
    assert ov.status_code == 200

    msgs = await client.get(f"/api/v1/physician/session/{sid}/messages")
    assert any(m["sender"] == "physician" for m in msgs.json())


@pytest.mark.asyncio
async def test_surgeon_pre_op(client, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.delenv("LLM_PROVIDER", raising=False)

    surgeon_json = json.dumps(
        {
            "response_text": "Pre-op checklist complete.",
            "action_items": ["NPO after midnight", "Check coagulation panel"],
            "risk_flags": [{"type": "VTE", "severity": "medium", "rationale": "prophylaxis needed"}],
            "confidence": "high",
        }
    )

    with patch("app.agents.surgeon.run_surgical", new=AsyncMock(return_value=surgeon_json)):
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
    assert r.status_code == 200
    data = r.json()
    assert len(data["action_items"]) > 0
    assert len(data["risk_flags"]) >= 1


@pytest.mark.asyncio
async def test_patient_profile_crud(client):
    r = await client.put(
        "/api/v1/patients/p5/profile",
        json={"age": 45, "sex": "F", "known_conditions_summary": "HTN"},
    )
    assert r.status_code == 200
    r = await client.get("/api/v1/patients/p5/profile")
    assert r.json()["age"] == 45
