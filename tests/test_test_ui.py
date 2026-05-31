"""Tests for the temporary static test UI mount."""

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.fixture
async def client():
    from app.database import init_db

    await init_db()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_test_ui_index_served(client):
    r = await client.get("/test-ui/")
    assert r.status_code == 200
    assert "TEMPORARY TEST UI" in r.text
    assert "mock-patient-001" in r.text
    assert "source-chip" in r.text
    assert "voice-select" in r.text
    assert "speakWithLocalTts" in r.text or "local-tts/speak" in r.text
    assert "PREFERRED_VOICE_PATTERNS" in r.text
