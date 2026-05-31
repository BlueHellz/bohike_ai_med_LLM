# Temporary AEGIS test UI

**Remove this directory before production.**

Minimal HTML/CSS/JS page for manual API testing (text + browser Web Speech STT + local Piper TTS).

## Enable

Set in `.env` (or export before starting the server):

```bash
TEST_UI_ENABLED=true
LOCAL_TTS_ENABLED=true
```

Default when unset: test-ui enabled; local TTS **disabled** until `LOCAL_TTS_ENABLED=true`.

## Local Piper voices

```bash
python3 local_tts/download_voices.py
pip install -r local_tts/requirements.txt
```

See [local_tts/README.md](../local_tts/README.md) for voice list and troubleshooting.

## Open

1. Start the API (example on port 8001):

   ```bash
   uvicorn app.main:app --reload --host 0.0.0.0 --port 8001
   ```

2. Open in a browser:

   **http://localhost:8001/test-ui/**

3. Optional: set **API base URL** to a relative path when served from the same host:

   `http://localhost:8001/api/v1` or `/api/v1` (same origin, no cross-origin requests).

## Behaviour

- On load: `POST /api/v1/sessions` with `patient_id: mock-patient-001`
- **Send**: `POST /api/v1/sessions/{session_id}/messages` with `channel: text`
- **Voice**: browser `SpeechRecognition` → `POST .../messages/stream` (SSE) with `channel: voice`
  (summary deferred server-side; see `VOICE_SKIP_SUMMARY`)
- **TTS**: voice replies auto-play via one Piper synthesis pass per reply (`POST /api/v1/local-tts/speak`);
  **Hear latest reply** replays the same WAV path. Voice picker lists `local_tts/voices.json` entries.
  Falls back to browser `speechSynthesis` if local TTS is off or fails (often more robotic).
  Piper is dev-only quality — not ChatGPT parity; production target is **Kokoro-82M** on-device
  (`docs/VOICE_PIPELINE.md` — sound quality section).
- Chat view with optional technical details under Advanced settings (default off)

## Requirements

- `DEEPSEEK_API_KEY` for live turns, **or** `DEV_STUB_LLM=true` in `.env` (see `.env.example`) when testing without an API key
- After editing `.env`, **restart the uvicorn server** so variables are reloaded
- On startup, the server logs `DeepSeek configured` when the key is present (the key value is never logged)
- Chrome or Edge recommended for Web Speech API
- For natural playback: Piper deps + downloaded ONNX models (see above)

## UI

- Chat-style conversation: user messages on the right, assistant replies on the left
- Assistant text is shown large and readable; status badges (Emergency, Physician notified) instead of raw JSON
- Friendly error message on failure; optional **Show technical details** under Advanced settings (off by default)
- Voice input appends the speech transcript as a message, then fetches the reply with `channel: voice`
- Voice dropdown shows active Piper voice; status line explains local vs browser fallback
