# AEGIS Medical AI Consultation Engine — Backend

Clinician-grade AI medical consultation API (patient, physician oversight, surgeon assistant tiers).

## Documentation

| Guide | Description |
|-------|-------------|
| [docs/GETTING_STARTED.md](docs/GETTING_STARTED.md) | Local setup, live DeepSeek verification, clinical smoke inputs |
| [docs/FINE_TUNING_PREP.md](docs/FINE_TUNING_PREP.md) | Dataset curation and fine-tuning readiness (pre-training) |
| [docs/AEGIS_TRAINING_BLUEPRINT.md](docs/AEGIS_TRAINING_BLUEPRINT.md) | Full training curriculum, datasets, and DeepSeek plan |
| [training/README.md](training/README.md) | Runnable pipeline scaffolds and synthetic clinic generator |

## Quick start

**Intel Mac (local Piper):** use `./scripts/run_aegis_py312.sh` with `.venv312` — see [local_tts/README.md](local_tts/README.md).

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Paste DEEPSEEK_API_KEY into .env locally (never commit secrets)
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Full onboarding: [docs/GETTING_STARTED.md](docs/GETTING_STARTED.md)

Health: `GET /health`

## Temporary test UI

A minimal static page under `test-ui/` is mounted at `/test-ui/` for manual API verification (not for production). Enable with `TEST_UI_ENABLED=true` (default on). See [test-ui/README.md](test-ui/README.md). Example: **http://localhost:8001/test-ui/**

## DeepSeek-only quick start

For patient consultation without Anthropic Claude:

```bash
cp .env.example .env
# Set in .env:
#   LLM_PROVIDER=deepseek
#   DEEPSEEK_API_KEY=<local key>
# Leave ANTHROPIC_API_KEY empty
uvicorn app.main:app --reload --port 8000
```

Behaviour in DeepSeek-only mode:

- Patient turns, review mode, rolling summary, and safety repair use DeepSeek only
- JSON parse failures retry DeepSeek once, then safety fallback (no Claude)
- Surgeon endpoints return HTTP 501 until `ANTHROPIC_API_KEY` is configured

See [docs/SURGEON_INTEGRATION.md](docs/SURGEON_INTEGRATION.md) for surgeon tier architecture.

## Environment variables

| Variable | Description |
|----------|-------------|
| `DEEPSEEK_API_KEY` | DeepSeek API key (required for live patient consultation) |
| `DEEPSEEK_BASE_URL` | Default `https://api.deepseek.com` |
| `DEEPSEEK_MODEL` | Default `deepseek-chat` |
| `LLM_PROVIDER` | Set `deepseek` to disable all Claude calls |
| `ANTHROPIC_API_KEY` | Claude key (surgeon tier + optional fallback when hybrid) |
| `CLAUDE_MODEL` | Default `claude-opus-4-5` |
| `DB_URL` | Default `sqlite+aiosqlite:///./aegis.db` |
| `PATIENT_DATA_PROVIDER` | `fixture` (default; legacy alias `mock`) or `http` (stub) |
| `PATIENT_BACKEND_URL` | Future external patient service base URL |
| `ROLLING_SUMMARY_MAX_TOKENS` | Rolling summary cap (default 300) |
| `RECENT_TURNS_K` | Recent turns loaded per turn (default 5) |
| `PATIENT_RESPONSE_MAX_TOKENS` | `patient_response_text` token budget (default 150) |
| `CLINICIAN_SUMMARY_MAX_TOKENS` | Clinician layer token budget |
| `MOCK_LLM` | Set `true` to require injected LLM callers (tests) |
| `LOG_LEVEL` | Logging level (default INFO) |

## Profile stub vs live consultation input

Two data sources feed a consultation turn; only one is stubbed today.

| Source | Scope | Provider |
|--------|-------|----------|
| **Fixture profile** | Static demographics and clinical summaries (age, sex, conditions, medications, allergies) | `FixturePatientDataProvider` / `fixtures/patients.json` until the external patient backend is connected |
| **Live consultation input** | All patient text and voice during the session (`POST /api/v1/sessions/{id}/messages`) | Request body — always real clinical input, never substituted from fixtures |

Consultation path (live input only for messages):

`TurnRequest` → `load_context` → `current_input` → `run_reasoning`

The stub profile is merged into `ClinicalContext.patient_profile` only. `current_input`
and persisted `SessionMessage` rows come from the client request.

### Fixture profiles (local dev)

Fixture profiles live in `fixtures/patients.json` (`mock-patient-001` … `003`).

```bash
curl http://localhost:8000/api/v1/patients/mock-patient-001/profile
```

`PUT /api/v1/patients/{id}/profile` writes to the local DB and overrides fixture data
for that patient ID. See `app/integrations/patient_data.py`.

Set `PATIENT_DATA_PROVIDER=http` to prepare for an external backend (raises
`NotImplementedError` until `PATIENT_BACKEND_URL` integration is built).

## Physician portal (placeholder)

REST endpoints under `/api/v1/physician/*` are ready for a future physician repo.
Optional header `X-Physician-Id` is accepted without validation.

Contract: [docs/PHYSICIAN_INTEGRATION.md](docs/PHYSICIAN_INTEGRATION.md)

## Voice client integration

Speech runs on the client (Sherpa-ONNX STT → REST → Kokoro-82M TTS). The backend
accepts transcribed text with `channel: "voice"`. Local dev test-ui uses Piper
(`en_US-lessac-medium`); **production on-device target is Kokoro-82M** (see
[docs/VOICE_PIPELINE.md](docs/VOICE_PIPELINE.md)).

Voice turns defer the rolling-summary LLM call when `VOICE_SKIP_SUMMARY=true` (default).
Stream tokens via `POST /api/v1/sessions/{id}/messages/stream` (SSE).

Details: [docs/VOICE_PIPELINE.md](docs/VOICE_PIPELINE.md)

## Consultation quality and training

Quality is achieved via structured prompts, safety enforcement, and rolling summary —
not mandatory fine-tuning on day one.

Details: [docs/TRAINING_AND_QUALITY.md](docs/TRAINING_AND_QUALITY.md) · Fine-tuning prep: [docs/FINE_TUNING_PREP.md](docs/FINE_TUNING_PREP.md) · Training blueprint: [docs/AEGIS_TRAINING_BLUEPRINT.md](docs/AEGIS_TRAINING_BLUEPRINT.md) · Pipeline: [training/README.md](training/README.md)

## API endpoints

### Sessions
- `POST /api/v1/sessions` — create session
- `POST /api/v1/sessions/{id}/messages` — consultation turn
- `POST /api/v1/sessions/{id}/messages/stream` — consultation turn (SSE token stream)
- `GET /api/v1/sessions/{id}/status` — session state
- `POST /api/v1/sessions/{id}/close` — close session

### Surgeon (requires Claude)
- `POST /api/v1/surgeon/query`
- `POST /api/v1/surgeon/pre-op`
- `POST /api/v1/surgeon/post-op`

### Physician
- `GET /api/v1/physician/alerts`
- `POST /api/v1/physician/alerts/{id}/ack`
- `GET /api/v1/physician/sessions/flagged`
- `GET /api/v1/physician/session/{id}/layer`
- `GET /api/v1/physician/session/{id}/messages`
- `POST /api/v1/physician/session/{id}/override`

### Patients
- `GET /api/v1/patients/{id}/profile`
- `PUT /api/v1/patients/{id}/profile`

## Tests

```bash
python -m pytest tests/ -v
```

## Docker

```bash
docker compose up --build
```

## Load test

```bash
locust -f locustfile.py --users 20 --spawn-rate 4 --run-time 5m
```
