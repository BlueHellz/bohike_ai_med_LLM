# Surgeon Tier Architecture

## Overview

The surgeon tier provides perioperative decision support via dedicated REST endpoints
and Claude-backed reasoning. Patient consultation (`/api/v1/sessions/*`) remains on
DeepSeek when `LLM_PROVIDER=deepseek`.

## Components

```
Client (surgeon UI)
    │
    ▼
POST /api/v1/surgeon/{query|pre-op|post-op}
    │
    ▼
app/agents/surgeon.py  →  run_surgical()
    │
    ▼
prompts/system_surgeon.txt  +  SurgicalContext
    │
    ▼
Anthropic Claude (requires ANTHROPIC_API_KEY)
```

## Request schema

`SurgeonRequest`:

| Field | Type | Description |
|-------|------|-------------|
| `surgeon_id` | string | Surgeon identifier |
| `surgical_context` | object | Procedure, phase, patient profile, notes |
| `query` | string | Natural-language surgeon question |

`surgical_context.phase`: `pre_op` | `intra_op` | `post_op`

## Response schema

`SurgeonResponse`:

| Field | Type |
|-------|------|
| `response_text` | string |
| `action_items` | string[] |
| `risk_flags` | RiskFlag[] |
| `confidence` | low \| medium \| high |

## DeepSeek-only deployment behaviour

When Claude is disabled (`LLM_PROVIDER=deepseek` or missing `ANTHROPIC_API_KEY`),
surgeon endpoints return **HTTP 501**:

```json
{
  "detail": "Surgeon tier unavailable until ANTHROPIC_API_KEY configured"
}
```

Routes, prompts (`system_surgeon.txt`), and handler code remain in place for future
activation without architectural changes.

## Enabling surgeon tier

1. Set a valid `ANTHROPIC_API_KEY` in local `.env`.
2. Remove or change `LLM_PROVIDER=deepseek` (or omit `LLM_PROVIDER` entirely).
3. Restart the API process.

## Future extensions

- Real-time intra-op streaming via WebSocket (stub at `/ws/sessions/{id}`)
- Integration with operative note EHR feeds
- Procedure-specific RAG over institutional protocols
