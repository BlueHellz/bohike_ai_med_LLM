# Physician Portal Integration Contract

## Purpose

This document defines the integration surface between the AEGIS consultation backend
and a future external physician portal repository. The backend exposes REST endpoints;
the portal consumes them and may later push webhook events.

Implementation stubs live in `app/integrations/physician_portal.py`.

## Authentication (future)

| Item | Status |
|------|--------|
| OAuth2 / SAML with portal IdP | Planned |
| Service-to-service API key | Planned |
| Optional header `X-Physician-Id` | Accepted today (no validation) |

All physician routes accept an optional `X-Physician-Id` header. Requests proceed
whether or not the header is present. Future auth middleware will require a validated
physician identity.

## REST endpoints (backend → portal consumer)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/physician/alerts` | Unacknowledged risk alerts |
| POST | `/api/v1/physician/alerts/{alert_id}/ack` | Acknowledge alert |
| GET | `/api/v1/physician/sessions/flagged` | Sessions requiring review |
| GET | `/api/v1/physician/session/{session_id}/layer` | Latest clinician layer |
| GET | `/api/v1/physician/session/{session_id}/messages` | Full session transcript |
| POST | `/api/v1/physician/session/{session_id}/override` | Physician annotation |

### Alert list response (example)

```json
[
  {
    "alert_id": "uuid",
    "patient_id": "string",
    "session_id": "string",
    "type": "chest_pain",
    "severity": "high",
    "rationale": "possible ACS",
    "created_at": "2026-05-29T12:00:00"
  }
]
```

### Override request

```json
{
  "text": "ECG reviewed — ST elevation noted."
}
```

## Webhook feed (future — portal → backend)

Planned event types:

- `alert.acknowledged`
- `session.review_completed`
- `override.created`

Payload schema and HMAC signing to be defined when the physician repo is connected.

## Environment variables (future)

| Variable | Description |
|----------|-------------|
| `PHYSICIAN_PORTAL_URL` | Base URL for outbound feed delivery |
| `PHYSICIAN_PORTAL_WEBHOOK_SECRET` | Shared secret for inbound webhooks |

These variables are not read by the current codebase.
