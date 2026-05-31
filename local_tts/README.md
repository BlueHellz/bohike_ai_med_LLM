# Local Piper TTS

High-quality **on-machine** text-to-speech for the AEGIS **test-ui** and local dev.
No cloud TTS APIs. Models live under `voices/piper/` (gitignored).

**`pip` does not install Python.** It installs packages into an existing interpreter only.
On Intel Mac with system Python 3.13, use **either** the Piper CLI setup below **or** install
[Python 3.12 for macOS from python.org](https://www.python.org/downloads/macos/) (no Homebrew).

## Voices

| ID | Name | Language | Quality |
|----|------|----------|---------|
| `en_US-lessac-medium` | Lessac (US, medium) | en-US | medium (default) |
| `en_US-amy-low` | Amy (US, low) | en-US | low |
| `en_GB-alan-medium` | Alan (GB, medium) | en-GB | medium |

Catalog: `local_tts/voices.json`.

## Step B — Recommended: Piper CLI (keeps Python 3.13 `.venv`)

From the repo root:

```bash
./scripts/setup_local_tts.sh
```

This downloads:

- `tools/piper/piper` — Piper CLI ([rhasspy/piper](https://github.com/rhasspy/piper/releases))
- `tools/piper/lib/` — phonemize runtime libraries (macOS CLI tarball omits dylibs; gitignored under `tools/piper/`)
- `voices/piper/*.onnx` — voice models if missing

Enable in `.env`:

```bash
LOCAL_TTS_ENABLED=true
```

Start the API (normal project venv):

```bash
./scripts/run_aegis.sh
```

Test:

```bash
python3 -c "from local_tts import synthesize; print(len(synthesize('Hello')))"
```

## Step A — Optional: Python 3.12 + piper-tts

1. Install **Python 3.12** from [python.org/downloads/macos](https://www.python.org/downloads/macos/).
2. Create a side venv (the API may continue using `.venv`; use `.venv312` for in-process synthesis):

```bash
python3.12 -m venv .venv312
source .venv312/bin/activate
pip install -r requirements.txt -r local_tts/requirements.txt
pip install --no-deps "piper-tts>=1.2.0"
python3 local_tts/download_voices.py
```

Optional server entrypoint with that venv only:

```bash
./scripts/run_aegis_py312.sh
```

## HTTP routes (dev, localhost)

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/local-tts/voices` | Catalog + `ready` flags |
| `POST` | `/api/v1/local-tts/speak` | JSON `{ "text", "voice_id?" }` → `audio/wav` |

Returns **503** when `LOCAL_TTS_ENABLED` is not `true`.

Optional env:

```bash
LOCAL_TTS_VOICES_DIR=/path/to/models
LOCAL_TTS_PIPER_BIN=/path/to/piper
LOCAL_TTS_PIPER_DIR=/path/to/piper/folder
```

## Python API

```python
from local_tts import synthesize

wav_bytes = synthesize("Hello.", voice_id="en_US-lessac-medium")
```

See `docs/VOICE_PIPELINE.md` (including **Sound quality expectations**) for why Piper ≠ ChatGPT
and for production on-device Kokoro guidance.

## Optional: Kokoro-82M (test-ui, higher quality)

Kokoro runs via **kokoro-onnx** (onnxruntime only — no torch). Works on Python 3.10–3.13 including
Intel Mac when model assets and deps are installed.

```bash
chmod +x ./scripts/setup_kokoro_tts.sh
./scripts/setup_kokoro_tts.sh
```

Downloads (~325 MB total, gitignored under `voices/kokoro/`):

- `kokoro-v1.0.onnx`
- `voices-v1.0.bin`

Enable in `.env` (Piper can stay enabled as fallback):

```bash
KOKORO_TTS_ENABLED=true
LOCAL_TTS_ENABLED=true
# LOCAL_TTS_DEFAULT_ENGINE=kokoro
```

Python deps only (if not installed by setup script):

```bash
pip install -r local_tts/kokoro_requirements.txt
```

Test:

```bash
python3 -c "from local_tts.kokoro_synthesize import synthesize; print(len(synthesize('Hello')))"
```

HTTP: `GET /api/v1/local-tts/engines`, `GET /api/v1/local-tts/voices?engine=kokoro`,
`POST /api/v1/local-tts/speak` with `{ "text", "voice_id?", "engine": "kokoro" }`.

Catalog: `local_tts/kokoro_voices.json` (default `af_sarah`).

If Kokoro import or synthesis fails on the host, test-ui shows an error and falls back to Piper
(when enabled) or browser TTS.
