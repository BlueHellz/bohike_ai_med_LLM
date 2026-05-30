"""Session lifecycle, context assembly, and rolling summary updates."""

import os
import uuid
from pathlib import Path

from sqlalchemy import desc, select

from app.integrations.patient_data import resolve_patient_profile
from app.models import AISummary, Session, SessionMessage
from app.schemas import ClinicalContext, ClinicianLayer, SessionMeta, Turn

PROMPTS_DIR = Path(__file__).resolve().parents[2] / "prompts"


def _recent_k() -> int:
    return int(os.getenv("RECENT_TURNS_K", "5"))


async def create_session(db, patient_id, channel="text", user_type="patient", mode="triage"):
    sid = str(uuid.uuid4())
    db.add(
        Session(
            id=sid,
            patient_id=patient_id,
            channel=channel,
            user_type=user_type,
            mode=mode,
        )
    )
    await db.commit()
    return sid


async def load_context(db, session_id, current_text, sender="patient") -> ClinicalContext:
    """Assemble ClinicalContext: stub profile + live current_input from the request."""
    session = await db.get(Session, session_id)
    if not session:
        raise ValueError(f"Session {session_id} not found")

    profile = await resolve_patient_profile(db, session.patient_id)

    stmt = (
        select(SessionMessage)
        .where(SessionMessage.session_id == session_id)
        .order_by(desc(SessionMessage.timestamp))
        .limit(_recent_k())
    )
    result = await db.execute(stmt)
    rows = list(reversed(result.scalars().all()))
    recent_turns = [Turn(sender=r.sender, text=r.text) for r in rows]

    channel = session.channel if session.channel in ("text", "voice") else "text"
    return ClinicalContext(
        patient_profile=profile,
        session_meta=SessionMeta(
            session_id=session_id,
            channel=channel,
            mode=session.mode,
            user_type=session.user_type,
        ),
        rolling_summary=session.rolling_summary or "",
        recent_turns=recent_turns,
        current_input=Turn(sender=sender, text=current_text),
    )


async def append_messages(db, session_id, patient_text, ai_text, channel="text"):
    db.add(
        SessionMessage(
            session_id=session_id, sender="patient", text=patient_text, channel=channel
        )
    )
    db.add(SessionMessage(session_id=session_id, sender="ai", text=ai_text, channel=channel))
    await db.commit()


async def append_physician_message(db, session_id, text, channel="text"):
    db.add(
        SessionMessage(session_id=session_id, sender="physician", text=text, channel=channel)
    )
    await db.commit()


async def save_clinician_layer(db, session_id, layer: ClinicianLayer):
    db.add(
        AISummary(
            session_id=session_id,
            clinician_summary=layer.summary,
            key_findings=layer.key_findings,
            differential_considerations=layer.differential_considerations,
            working_diagnosis_areas=layer.working_diagnosis_areas,
            risk_flags=[f.model_dump() for f in layer.risk_flags],
            followup_questions=layer.followup_questions,
            recommended_physician_actions=layer.recommended_physician_actions,
            confidence_level=layer.confidence_level,
        )
    )
    await db.commit()


async def update_rolling_summary(db, session_id, llm_summariser, old_summary, new_turns):
    max_tokens = int(os.getenv("ROLLING_SUMMARY_MAX_TOKENS", "300"))
    sys_prompt = (PROMPTS_DIR / "system_summarise.txt").read_text().format(max_tokens=max_tokens)
    turns_text = "\n".join(f"{t.sender}: {t.text}" for t in new_turns)
    new_sum = await llm_summariser(
        sys_prompt,
        f"EXISTING SUMMARY:\n{old_summary}\n\nNEW TURNS:\n{turns_text}",
    )
    session = await db.get(Session, session_id)
    session.rolling_summary = new_sum.strip()
    await db.commit()
