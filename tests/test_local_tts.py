"""Tests for local Piper TTS routes (dev-only, gated by env)."""

import importlib
from pathlib import Path
from unittest.mock import patch

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
async def test_local_tts_speak_disabled_returns_503(client, monkeypatch):
    monkeypatch.delenv("LOCAL_TTS_ENABLED", raising=False)
    r = await client.post(
        "/api/v1/local-tts/speak",
        json={"text": "Hello"},
    )
    assert r.status_code == 503
    assert "disabled" in r.json()["detail"].lower()


@pytest.mark.asyncio
async def test_local_tts_voices_disabled_returns_503(client, monkeypatch):
    monkeypatch.setenv("LOCAL_TTS_ENABLED", "false")
    r = await client.get("/api/v1/local-tts/voices")
    assert r.status_code == 503


@pytest.mark.asyncio
async def test_local_tts_speak_enabled_returns_wav(client, monkeypatch):
    monkeypatch.setenv("LOCAL_TTS_ENABLED", "true")
    fake_wav = b"RIFFfakeWAVdata"

    with patch("app.api.local_tts_routes.synthesize", return_value=fake_wav):
        r = await client.post(
            "/api/v1/local-tts/speak",
            json={"text": "Hello there", "voice_id": "en_US-lessac-medium"},
        )

    assert r.status_code == 200
    assert r.headers["content-type"].startswith("audio/wav")
    assert r.content == fake_wav


@pytest.mark.asyncio
async def test_local_tts_voices_enabled_lists_catalog(client, monkeypatch):
    monkeypatch.setenv("LOCAL_TTS_ENABLED", "true")
    r = await client.get("/api/v1/local-tts/voices")
    assert r.status_code == 200
    body = r.json()
    assert body["default_voice_id"] == "en_US-lessac-medium"
    ids = {v["id"] for v in body["voices"]}
    assert "en_US-lessac-medium" in ids
    assert "en_US-amy-low" in ids


def test_synthesize_empty_text_raises():
    from local_tts.synthesize import LocalTtsError, synthesize

    with pytest.raises(LocalTtsError, match="empty"):
        synthesize("   ")


def test_piper_binary_default_path():
    from local_tts.synthesize import piper_cli_dir

    assert piper_cli_dir().name == "piper"
    assert piper_cli_dir().parent.name == "tools"


def test_synthesize_cli_fallback(monkeypatch, tmp_path):
    synth_module = importlib.import_module("local_tts.synthesize")
    from local_tts.synthesize import synthesize

    fake_bin = tmp_path / "piper"
    fake_bin.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    fake_bin.chmod(0o755)

    onnx = tmp_path / "en_US-lessac-medium.onnx"
    cfg = tmp_path / "en_US-lessac-medium.onnx.json"
    onnx.write_bytes(b"onnx")
    cfg.write_text("{}", encoding="utf-8")

    monkeypatch.setenv("LOCAL_TTS_VOICES_DIR", str(tmp_path))
    monkeypatch.setenv("LOCAL_TTS_PIPER_BIN", str(fake_bin))

    def fake_run(cmd, **kwargs):
        out_file = Path(cmd[cmd.index("--output_file") + 1])
        out_file.write_bytes(b"RIFFcli")

        class R:
            returncode = 0
            stdout = ""
            stderr = ""

        return R()

    monkeypatch.setattr(synth_module.subprocess, "run", fake_run)
    assert synthesize("Hello") == b"RIFFcli"


def test_synthesize_missing_backend_message(monkeypatch, tmp_path):
    synth_module = importlib.import_module("local_tts.synthesize")
    from local_tts.synthesize import LocalTtsError, synthesize

    onnx = tmp_path / "en_US-lessac-medium.onnx"
    cfg = tmp_path / "en_US-lessac-medium.onnx.json"
    onnx.write_bytes(b"onnx")
    cfg.write_text("{}", encoding="utf-8")

    monkeypatch.setenv("LOCAL_TTS_VOICES_DIR", str(tmp_path))
    monkeypatch.setenv("LOCAL_TTS_PIPER_BIN", "")
    monkeypatch.setattr(synth_module, "piper_binary", lambda: None)

    with pytest.raises(LocalTtsError, match="setup_local_tts"):
        synthesize("Hello")
