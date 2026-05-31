"""Voice channel defers blocking rolling summary."""

import asyncio
import time
from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.agents.reasoning import reset_llm_callers, set_llm_callers
from app.agents.voice_config import patient_defer_summary_enabled, should_defer_summary
from app.main import app
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


def test_patient_defer_summary_defaults_true(monkeypatch):
    monkeypatch.delenv("PATIENT_DEFER_SUMMARY", raising=False)
    monkeypatch.delenv("VOICE_SKIP_SUMMARY", raising=False)
    assert patient_defer_summary_enabled() is True
    assert should_defer_summary("voice") is True
    assert should_defer_summary("text") is True


@pytest.mark.asyncio
async def test_voice_turn_returns_before_slow_summary(client, monkeypatch):
    monkeypatch.setenv("VOICE_SKIP_SUMMARY", "true")

    async def mock_deepseek(_s, _u, max_tokens=900, **kwargs):
        if "EXISTING SUMMARY:" in _u:
            await asyncio.sleep(3)
            return "Updated summary."
        return make_reasoning_json("Short voice reply.")

    set_llm_callers(deepseek_fn=mock_deepseek)

    r = await client.post(
        "/api/v1/sessions",
        json={"patient_id": "p-voice-fast", "channel": "voice"},
    )
    sid = r.json()["session_id"]

    t0 = time.monotonic()
    turn = await client.post(
        f"/api/v1/sessions/{sid}/messages",
        json={
            "session_id": sid,
            "user_id": "p-voice-fast",
            "text": "I have a headache",
            "channel": "voice",
        },
    )
    voice_elapsed = time.monotonic() - t0

    assert turn.status_code == 200
    assert voice_elapsed < 2.0

    t0 = time.monotonic()
    turn_text = await client.post(
        f"/api/v1/sessions/{sid}/messages",
        json={
            "session_id": sid,
            "user_id": "p-voice-fast",
            "text": "It started yesterday",
            "channel": "text",
        },
    )
    text_elapsed = time.monotonic() - t0

    assert turn_text.status_code == 200
    assert text_elapsed < 2.0


@pytest.mark.asyncio
async def test_voice_turn_schedules_summary_not_blocking_update(client, monkeypatch):
    monkeypatch.setenv("VOICE_SKIP_SUMMARY", "true")

    async def mock_deepseek(_s, _u, max_tokens=900, **kwargs):
        return make_reasoning_json("Voice reply.")

    set_llm_callers(deepseek_fn=mock_deepseek)

    with patch("app.api.routes.schedule_rolling_summary") as sched, patch(
        "app.api.routes.update_rolling_summary"
    ) as blocking:
        r = await client.post(
            "/api/v1/sessions",
            json={"patient_id": "p-sched", "channel": "voice"},
        )
        sid = r.json()["session_id"]
        resp = await client.post(
            f"/api/v1/sessions/{sid}/messages",
            json={
                "session_id": sid,
                "user_id": "p-sched",
                "text": "hello",
                "channel": "voice",
            },
        )
        assert resp.status_code == 200
        sched.assert_called_once()
        blocking.assert_not_called()
