"""Physician alert persistence from consultation safety decisions."""

import uuid
from datetime import datetime

from app.models import Alert, Session
from app.schemas import ReasoningOutput


async def process_alerts(db, output: ReasoningOutput, patient_id, session_id) -> list[dict]:
    alerts = []
    flags = [f for f in output.clinician_layer.risk_flags if f.severity in ("medium", "high")]

    for flag in flags:
        rec = Alert(
            id=str(uuid.uuid4()),
            patient_id=patient_id,
            session_id=session_id,
            flag_type=flag.type,
            severity=flag.severity,
            rationale=flag.rationale,
            created_at=datetime.utcnow(),
        )
        db.add(rec)
        alerts.append(
            {
                "alert_id": rec.id,
                "type": flag.type,
                "severity": flag.severity,
                "rationale": flag.rationale,
            }
        )

    if output.safety.requires_physician_review or output.safety.emergency_detected:
        session = await db.get(Session, session_id)
        if session:
            session.requires_review = True
            session.emergency_flag = output.safety.emergency_detected

    await db.commit()
    return alerts
