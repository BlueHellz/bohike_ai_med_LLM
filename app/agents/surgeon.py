"""Surgeon-tier request handling (Claude-backed when configured)."""

import json

from app.agents.reasoning import run_surgical
from app.schemas import RiskFlag, SurgeonRequest, SurgeonResponse


async def handle_surgeon(req: SurgeonRequest) -> SurgeonResponse:
    raw = await run_surgical(req.surgical_context, req.query)
    try:
        data = json.loads(raw)
        return SurgeonResponse(
            response_text=data.get(
                "response_text", "Unable to process — consult clinical reference."
            ),
            action_items=data.get("action_items", []),
            risk_flags=[RiskFlag(**f) for f in data.get("risk_flags", [])],
            confidence=data.get("confidence", "low"),
        )
    except Exception:
        return SurgeonResponse(
            response_text="Unable to process this query. Please consult clinical reference materials.",
            action_items=[],
            risk_flags=[],
            confidence="low",
        )
