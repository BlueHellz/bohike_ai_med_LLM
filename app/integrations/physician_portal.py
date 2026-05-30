"""
Physician portal integration stub.

Future responsibilities (not implemented in this repository):

- Authentication: OAuth2 / SAML handoff with the physician portal identity provider.
- Webhook ingestion: receive alert acknowledgements, session flags, and override events
  from the external physician dashboard.
- Feed export: push clinician-layer summaries and risk flags to the physician UI feed.

The REST endpoints under ``/api/v1/physician/*`` in ``app.api.routes`` serve as the
integration contract surface. Optional header ``X-Physician-Id`` may be supplied by
callers until portal authentication is wired.
"""

from typing import Any


async def authenticate_physician(_credentials: dict[str, Any]) -> str | None:
    """Validate portal credentials and return physician identifier. Not implemented."""
    raise NotImplementedError("Physician portal authentication is not configured.")


async def push_alert_to_portal(_alert_payload: dict[str, Any]) -> None:
    """Deliver an alert record to the external physician feed. Not implemented."""
    raise NotImplementedError("Physician portal webhook delivery is not configured.")


async def receive_portal_webhook(_payload: dict[str, Any]) -> dict[str, Any]:
    """Process inbound webhook events from the physician portal. Not implemented."""
    raise NotImplementedError("Physician portal webhook ingestion is not configured.")
