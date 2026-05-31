"""Tests for LLM configuration errors and API error exposure."""

import pytest
from httpx import ASGITransport, AsyncClient

from app.agents.reasoning import reset_llm_callers
from app.main import app


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


@pytest.mark.asyncio
async def test_missing_deepseek_key_returns_503(client, monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setenv("DEV_STUB_LLM", "false")
    monkeypatch.setenv("ENV", "development")

    r = await client.post("/api/v1/sessions", json={"patient_id": "p-missing-key", "channel": "text"})
    sid = r.json()["session_id"]

    r = await client.post(
        f"/api/v1/sessions/{sid}/messages",
        json={
            "session_id": sid,
            "user_id": "p-missing-key",
            "text": "I have a headache",
        },
    )
    assert r.status_code == 503
    assert "DEEPSEEK_API_KEY" in r.json()["detail"]


@pytest.mark.asyncio
async def test_dev_stub_headache_turn(client, monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setenv("DEV_STUB_LLM", "true")
    monkeypatch.setenv("ENV", "development")

    r = await client.post("/api/v1/sessions", json={"patient_id": "p-stub", "channel": "text"})
    sid = r.json()["session_id"]

    r = await client.post(
        f"/api/v1/sessions/{sid}/messages",
        json={
            "session_id": sid,
            "user_id": "p-stub",
            "text": "I have a headache",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert "headache" in body["patient_response_text"].lower()
