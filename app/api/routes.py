"""REST API routes for sessions, surgeon, physician, and patient endpoints."""

import json
import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.alert import process_alerts
from app.agents.reasoning import (
    build_reasoning_prompts,
    call_deepseek,
    is_claude_enabled,
    run_reasoning,
    stream_deepseek,
)
from app.agents.routing import route
from app.agents.safety import validate_and_enforce
from app.agents.session import (
    append_messages,
    append_physician_message,
    create_session,
    load_context,
    save_clinician_layer,
    schedule_rolling_summary,
    update_rolling_summary,
)
from app.agents.surgeon import handle_surgeon
from app.agents.voice import normalize_voice_turn
from app.agents.voice_config import should_defer_summary
from app.llm_errors import LlmConfigurationError, LlmUpstreamError
from app.database import get_db
from app.integrations.patient_data import resolve_patient_profile
from app.models import AISummary, Alert, PatientProfileDB, Session, SessionMessage
from app.schemas import (
    CreateSessionRequest,
    OverrideRequest,
    PatientProfile,
    SurgeonRequest,
    TurnRequest,
    TurnResponse,
)

router = APIRouter()
logger = logging.getLogger(__name__)

SURGEON_UNAVAILABLE_DETAIL = (
    "Surgeon tier unavailable until ANTHROPIC_API_KEY configured"
)


def _summary_llm():
    return lambda s, u: call_deepseek(s, u, max_tokens=350, json_mode=False)


async def _apply_rolling_summary(
    db: AsyncSession,
    req: TurnRequest,
    channel: str,
    ctx,
) -> None:
    summariser = _summary_llm()
    new_turns = ctx.recent_turns + [ctx.current_input]
    if should_defer_summary(channel):
        schedule_rolling_summary(
            req.session_id,
            summariser,
            ctx.rolling_summary,
            new_turns,
        )
        return
    await update_rolling_summary(
        db,
        req.session_id,
        llm_summariser=summariser,
        old_summary=ctx.rolling_summary,
        new_turns=new_turns,
    )


async def _persist_turn(
    db: AsyncSession,
    req: TurnRequest,
    channel: str,
    ctx,
    text: str,
    output,
) -> TurnResponse:
    await append_messages(db, req.session_id, text, output.patient_response_text, channel)
    await save_clinician_layer(db, req.session_id, output.clinician_layer)
    await _apply_rolling_summary(db, req, channel, ctx)

    alerts = await process_alerts(db, output, req.user_id, req.session_id)

    ui_hints = {}
    if output.safety.emergency_detected:
        ui_hints["show_emergency_banner"] = True
    elif output.safety.should_escalate:
        ui_hints["show_escalation_banner"] = True
    if alerts:
        ui_hints["physician_notified"] = True

    return TurnResponse(
        patient_response_text=output.patient_response_text,
        ui_hints=ui_hints,
        session_id=req.session_id,
        citations=list(output.source_citations or []),
    )


async def _prepare_turn(req: TurnRequest, db: AsyncSession):
    """Load context, apply citation_depth override; returns text, channel, ctx, mode, model."""
    text, channel = normalize_voice_turn(req.text, req.channel)
    ctx = await load_context(
        db, req.session_id, text, sender="patient", turn_channel=channel
    )

    if req.citation_depth:
        ctx.session_meta.citation_depth = req.citation_depth
        session = await db.get(Session, req.session_id)
        if session:
            session.citation_depth = req.citation_depth
            await db.commit()

    mode, model = route(ctx)
    ctx.session_meta.mode = mode
    return text, channel, ctx, mode, model


async def handle_turn(req: TurnRequest, db: AsyncSession) -> TurnResponse:
    """Process a consultation turn; patient message text is never substituted from fixtures."""
    text, channel, ctx, mode, model = await _prepare_turn(req, db)

    raw_json, _used_claude = await run_reasoning(ctx, mode, model)

    repair_fn = lambda s, u: call_deepseek(s, u)
    output = await validate_and_enforce(raw_json, repair_fn)

    return await _persist_turn(db, req, channel, ctx, text, output)


async def _ensure_session_open(session_id: str, req: TurnRequest, db: AsyncSession) -> Session:
    if req.session_id != session_id:
        raise HTTPException(400, "session_id mismatch")
    session = await db.get(Session, session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    if session.closed:
        raise HTTPException(400, "Session is closed")
    return session


def _require_surgeon_tier():
    if not is_claude_enabled():
        raise HTTPException(status_code=501, detail=SURGEON_UNAVAILABLE_DETAIL)


@router.post("/sessions")
async def create_session_endpoint(body: CreateSessionRequest, db: AsyncSession = Depends(get_db)):
    sid = await create_session(
        db,
        body.patient_id,
        channel=body.channel,
        user_type=body.user_type,
        mode=body.mode,
        citation_depth=body.citation_depth,
    )
    return {"session_id": sid}


@router.post("/sessions/{session_id}/messages", response_model=TurnResponse)
async def post_message(
    session_id: str, req: TurnRequest, db: AsyncSession = Depends(get_db)
):
    await _ensure_session_open(session_id, req, db)
    return await handle_turn(req, db)


@router.post("/sessions/{session_id}/messages/stream")
async def post_message_stream(
    session_id: str, req: TurnRequest, db: AsyncSession = Depends(get_db)
):
    """SSE stream of reasoning JSON chunks; final event includes TurnResponse fields."""
    await _ensure_session_open(session_id, req, db)

    async def event_generator():
        try:
            text, channel, ctx, mode, model = await _prepare_turn(req, db)
            if model == "claude" and is_claude_enabled():
                raw_json, _ = await run_reasoning(ctx, mode, model)
                yield f"data: {json.dumps({'type': 'chunk', 'delta': raw_json})}\n\n"
            else:
                system, user, max_tokens = build_reasoning_prompts(ctx, mode)
                parts: list[str] = []
                async for delta in stream_deepseek(system, user, max_tokens=max_tokens):
                    parts.append(delta)
                    yield f"data: {json.dumps({'type': 'chunk', 'delta': delta})}\n\n"
                raw_json = "".join(parts)

            repair_fn = lambda s, u: call_deepseek(s, u)
            output = await validate_and_enforce(raw_json, repair_fn)
            response = await _persist_turn(db, req, channel, ctx, text, output)
            yield f"data: {json.dumps({'type': 'done', 'response': response.model_dump()})}\n\n"
        except (LlmConfigurationError, LlmUpstreamError) as exc:
            logger.exception("Streaming turn failed")
            yield f"data: {json.dumps({'type': 'error', 'detail': str(exc)})}\n\n"
        except Exception as exc:
            logger.exception("Streaming turn failed")
            yield f"data: {json.dumps({'type': 'error', 'detail': str(exc)})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/sessions/{session_id}/status")
async def session_status(session_id: str, db: AsyncSession = Depends(get_db)):
    session = await db.get(Session, session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    return {
        "session_id": session.id,
        "patient_id": session.patient_id,
        "mode": session.mode,
        "channel": session.channel,
        "requires_review": session.requires_review,
        "emergency_flag": session.emergency_flag,
        "closed": session.closed,
        "rolling_summary": session.rolling_summary,
    }


@router.post("/sessions/{session_id}/close")
async def close_session(session_id: str, db: AsyncSession = Depends(get_db)):
    session = await db.get(Session, session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    session.closed = True
    await db.commit()
    return {"session_id": session_id, "closed": True}


@router.post("/surgeon/query")
async def surgeon_query(req: SurgeonRequest):
    _require_surgeon_tier()
    return await handle_surgeon(req)


@router.post("/surgeon/pre-op")
async def surgeon_pre_op(req: SurgeonRequest):
    _require_surgeon_tier()
    req.surgical_context.phase = "pre_op"
    return await handle_surgeon(req)


@router.post("/surgeon/post-op")
async def surgeon_post_op(req: SurgeonRequest):
    _require_surgeon_tier()
    req.surgical_context.phase = "post_op"
    return await handle_surgeon(req)


@router.get("/physician/alerts")
async def physician_alerts(
    db: AsyncSession = Depends(get_db),
    x_physician_id: Optional[str] = Header(None, alias="X-Physician-Id"),
):
    stmt = select(Alert).where(Alert.acknowledged == False).order_by(desc(Alert.created_at))  # noqa: E712
    result = await db.execute(stmt)
    rows = result.scalars().all()
    return [
        {
            "alert_id": a.id,
            "patient_id": a.patient_id,
            "session_id": a.session_id,
            "type": a.flag_type,
            "severity": a.severity,
            "rationale": a.rationale,
            "created_at": a.created_at.isoformat() if a.created_at else None,
        }
        for a in rows
    ]


@router.post("/physician/alerts/{alert_id}/ack")
async def ack_alert(
    alert_id: str,
    db: AsyncSession = Depends(get_db),
    x_physician_id: Optional[str] = Header(None, alias="X-Physician-Id"),
):
    alert = await db.get(Alert, alert_id)
    if not alert:
        raise HTTPException(404, "Alert not found")
    alert.acknowledged = True
    await db.commit()
    return {"alert_id": alert_id, "acknowledged": True}


@router.get("/physician/sessions/flagged")
async def flagged_sessions(
    db: AsyncSession = Depends(get_db),
    x_physician_id: Optional[str] = Header(None, alias="X-Physician-Id"),
):
    stmt = select(Session).where(Session.requires_review == True)  # noqa: E712
    result = await db.execute(stmt)
    rows = result.scalars().all()
    return [
        {
            "session_id": s.id,
            "patient_id": s.patient_id,
            "emergency_flag": s.emergency_flag,
            "mode": s.mode,
            "created_at": s.created_at.isoformat() if s.created_at else None,
        }
        for s in rows
    ]


@router.get("/physician/session/{session_id}/layer")
async def physician_layer(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    x_physician_id: Optional[str] = Header(None, alias="X-Physician-Id"),
):
    stmt = (
        select(AISummary)
        .where(AISummary.session_id == session_id)
        .order_by(desc(AISummary.timestamp))
        .limit(1)
    )
    result = await db.execute(stmt)
    summary = result.scalar_one_or_none()
    if not summary:
        raise HTTPException(404, "No clinician layer found")
    return {
        "summary": summary.clinician_summary,
        "key_findings": summary.key_findings,
        "differential_considerations": summary.differential_considerations,
        "working_diagnosis_areas": summary.working_diagnosis_areas,
        "risk_flags": summary.risk_flags,
        "followup_questions": summary.followup_questions,
        "recommended_physician_actions": summary.recommended_physician_actions,
        "confidence_level": summary.confidence_level,
        "timestamp": summary.timestamp.isoformat() if summary.timestamp else None,
    }


@router.get("/physician/session/{session_id}/messages")
async def physician_messages(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    x_physician_id: Optional[str] = Header(None, alias="X-Physician-Id"),
):
    stmt = (
        select(SessionMessage)
        .where(SessionMessage.session_id == session_id)
        .order_by(SessionMessage.timestamp)
    )
    result = await db.execute(stmt)
    rows = result.scalars().all()
    return [
        {
            "id": m.id,
            "sender": m.sender,
            "text": m.text,
            "channel": m.channel,
            "timestamp": m.timestamp.isoformat() if m.timestamp else None,
        }
        for m in rows
    ]


@router.post("/physician/session/{session_id}/override")
async def physician_override(
    session_id: str,
    body: OverrideRequest,
    db: AsyncSession = Depends(get_db),
    x_physician_id: Optional[str] = Header(None, alias="X-Physician-Id"),
):
    session = await db.get(Session, session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    await append_physician_message(db, session_id, body.text)
    return {"session_id": session_id, "stored": True}


@router.get("/patients/{patient_id}/profile", response_model=PatientProfile)
async def get_profile(patient_id: str, db: AsyncSession = Depends(get_db)):
    return await resolve_patient_profile(db, patient_id)


@router.put("/patients/{patient_id}/profile", response_model=PatientProfile)
async def put_profile(
    patient_id: str, profile: PatientProfile, db: AsyncSession = Depends(get_db)
):
    row = await db.get(PatientProfileDB, patient_id)
    if not row:
        row = PatientProfileDB(patient_id=patient_id)
        db.add(row)
    row.age = profile.age
    row.sex = profile.sex
    row.known_conditions_summary = profile.known_conditions_summary
    row.medications_summary = profile.medications_summary
    row.allergies_summary = profile.allergies_summary
    row.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(row)
    return profile
