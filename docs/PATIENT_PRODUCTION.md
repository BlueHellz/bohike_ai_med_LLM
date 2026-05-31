# Patient-only production readiness (AEGIS MVP)

This document describes how to ship the **patient consultation** layer only. Physician portal and surgeon (enterprise) tiers are intentionally out of scope until later.

## What “production-ready” means here

| In scope now | Later |
|--------------|-------|
| Patient can start a session and get multi-turn medical consultation | Physician dashboard |
| Disclaimers, safety layer, citations | Surgeon / Claude review tier |
| Text + optional local voice (Piper) in test-ui or your frontend | Fine-tuned proprietary model |
| DeepSeek reasoning with rolling context | Real EHR / patient backend HTTP |

Accuracy comes from **prompts + safety validation + human disclaimers**, not from skipping the clinical schema. Latency comes from **one blocking LLM call per turn** and **streaming to the client**.

## Medical-only scope guardrails

Patient turns are constrained to **health and medical consultation**:

- `prompts/system_patient.txt` defines SCOPE, anti-rambling, and a brief off-topic redirect template within the `{patient_max}` token budget.
- `validate_and_enforce` runs a lightweight rule-based off-topic check (no extra LLM call): clearly non-medical user messages (sports trivia, history, entertainment, etc.) receive a fixed redirect in `patient_response_text`.
- Medical-adjacent context is allowed (e.g. injury during sport, occupational exposure). `safety.off_topic_detected` and `ui_hints.off_topic_redirect` signal redirects to the frontend.
- `PATIENT_RESPONSE_MAX_TOKENS=150` still applies; redirects and trims end on complete sentence boundaries.

## Latency (text and voice)

Each turn used to wait for **two** DeepSeek calls (reasoning + rolling summary). Patient turns now default to:

- `PATIENT_DEFER_SUMMARY=true` — summary updates in the background after the HTTP response
- `PATIENT_RESPONSE_MAX_TOKENS=150` — patient-visible prose in `patient_response_text` (prompt + trim)
- `PATIENT_REASONING_MAX_TOKENS=600` (text), `VOICE_REASONING_MAX_TOKENS=550` (voice) — full JSON completion cap
- Test-ui and recommended frontend path: `POST .../messages/stream` (SSE) so the user sees tokens as they arrive

Typical perceived improvement: **~15–45 seconds removed** from the wait before the first visible text (summary no longer blocks).

Remaining latency is mostly **DeepSeek API time** and, for voice, **Piper synthesis** after the reply text is ready.

### Recommended `.env` for patient MVP

```env
LLM_PROVIDER=deepseek
DEEPSEEK_API_KEY=<your-key>
PATIENT_DEFER_SUMMARY=true
PATIENT_RESPONSE_MAX_TOKENS=150
PATIENT_REASONING_MAX_TOKENS=600
VOICE_REASONING_MAX_TOKENS=550
VOICE_PATIENT_RESPONSE_MAX_TOKENS=150
RECENT_TURNS_K=5
ROLLING_SUMMARY_MAX_TOKENS=300

# Production: disable bundled test UI
TEST_UI_ENABLED=false

# Optional local voice in your app (not required for text-only MVP)
LOCAL_TTS_ENABLED=false
```

Restart uvicorn after changing `.env`.

## Frontend integration (your app repo)

1. **Base URL** — e.g. `https://api.yourdomain.com/api/v1` (AEGIS on port **8001** locally; do not point at NeuroSync on 8000).
2. **Create session** — `POST /sessions` with `{ "patient_id": "...", "channel": "text" | "voice" }`.
3. **Send messages** — prefer `POST /sessions/{id}/messages/stream` with `Accept: text/event-stream`.
   - Events: `{ "type": "chunk", "delta": "..." }` then `{ "type": "done", "response": { ... TurnResponse } }`.
4. **Display** — show `patient_response_text`; keep `disclaimer` visible; optional `citations`.
5. **Voice** — after `done`, call `POST /local-tts/synthesize` with spoken text (server strips disclaimer blocks) or use client-side TTS (e.g. Kokoro in production frontend).

## Security and ops checklist

- [ ] `TEST_UI_ENABLED=false` in production
- [ ] `DEV_STUB_LLM=false` and valid `DEEPSEEK_API_KEY`
- [ ] CORS restricted to your frontend origin (configure in `app/main.py` when deploying)
- [ ] HTTPS termination at reverse proxy
- [ ] Rate limiting / auth at gateway (not built into MVP API)
- [ ] Postgres `DB_URL` instead of SQLite for multi-instance deploy
- [ ] Rotate any API key that was ever pasted into chat or committed

## Prove the concept (not a chatbot)

1. Run smoke eval: `python scripts/eval_clinical_smoke.py` (with API key set).
2. Manually test 3–5 scenarios: chest pain red flags, medication question, chronic follow-up — confirm disclaimers and escalation language.
3. Tune `prompts/system_patient.txt` for tone and brevity; avoid removing safety fields from JSON schema.

## What not to build yet

- Surgeon routes (`501` without Claude) — enterprise later
- Physician portal stubs — wire when portal exists
- Full training pipeline — improves accuracy over time; not required for first patient MVP

## Local run (developer)

```bash
cd /path/to/a.i_med_back-end
source .venv/bin/activate
uvicorn app.main:app --reload --port 8001
```

Health: `GET http://localhost:8001/health` → `"service": "aegis-medical-consultation-engine"`.

Test-ui (dev only): `TEST_UI_ENABLED=true` → `http://localhost:8001/test-ui/`.
