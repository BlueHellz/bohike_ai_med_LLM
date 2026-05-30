"""REST API routes for sessions, surgeon, physician, and patient endpoints."""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.alert import process_alerts
from app.agents.reasoning import call_deepseek, is_claude_enabled, run_reasoning
from app.agents.routing import route
from app.agents.safety import validate_and_enforce
from app.agents.session import (
    append_messages,
    append_physician_message,
    create_session,
    load_context,
    save_clinician_layer,
    update_rolling_summary,
)
from app.agents.surgeon import handle_surgeon
from app.agents.voice import normalize_voice_turn
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

SURGEON_UNAVAILABLE_DETAIL = (
    "Surgeon tier unavailable until ANTHROPIC_API_KEY configured"
)


async def handle_turn(req: TurnRequest, db: AsyncSession) -> TurnResponse:
    """Process a live consultation turn; patient text is never fixture-substituted."""
    text, channel = normalize_voice_turn(req.text, req.channel)
    ctx = await load_context(db, req.session_id, text, sender="patient")

    mode, model = route(ctx)
    ctx.session_meta.mode = mode

    raw_json, _used_claude = await run_reasoning(ctx, mode, model)

    repair_fn = lambda s, u: call_deepseek(s, u)
    output = await validate_and_enforce(raw_json, repair_fn)

    await append_messages(db, req.session_id, text, output.patient_response_text, channel)
    await save_clinician_layer(db, req.session_id, output.clinician_layer)
    await update_rolling_summary(
        db,
        req.session_id,
        llm_summariser=lambda s, u: call_deepseek(s, u, max_tokens=350),
        old_summary=ctx.rolling_summary,
        new_turns=ctx.recent_turns + [ctx.current_input],
    )

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
    )


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
    )
    return {"session_id": sid}


@router.post("/sessions/{session_id}/messages", response_model=TurnResponse)
async def post_message(
    session_id: str, req: TurnRequest, db: AsyncSession = Depends(get_db)
):
    if req.session_id != session_id:
        raise HTTPException(400, "session_id mismatch")
    session = await db.get(Session, session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    if session.closed:
        raise HTTPException(400, "Session is closed")
    return await handle_turn(req, db)


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
