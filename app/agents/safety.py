"""Post-LLM safety validation, content enforcement, and structured fallback."""

import json
import re
from pathlib import Path

from app.schemas import ClinicianLayer, ReasoningOutput, SafetyDecision

PROMPTS_DIR = Path(__file__).resolve().parents[2] / "prompts"

DIAGNOSIS_RE = [
    r"\byou have\b.{0,50}\b(disease|syndrome|disorder|condition|cancer|diabetes|"
    r"infection|hypertension|failure|tumou?r|lesion)\b",
    r"\bdiagnosis(?:\s+is|\s*:)\b",
    r"\bdiagnosed with\b",
    r"\bthis is\s+(?:a|an)\s+\w+\s+(?:disease|syndrome|disorder)\b",
]
DOSING_RE = [
    r"\b\d+\s*(?:mg|mcg|ml|units?|tablets?)\b.{0,40}\b(?:take|daily|twice|tds|qds|per day)\b",
    r"\bprescri(?:be|ption)\b",
    r"\btake\s+\d+",
    r"\badminister\s+\d+",
]

EMERGENCY_DISCLAIMER = (
    "If you believe this is a medical emergency, call emergency services "
    "(911, 999, 112, or your local number) immediately. "
    "Do not wait for further advice."
)
STANDARD_DISCLAIMER = (
    "This information is not a substitute for professional medical advice. "
    "Please consult your doctor for a proper evaluation."
)


def _violations(text: str) -> list[str]:
    v = []
    for p in DIAGNOSIS_RE:
        if re.search(p, text, re.IGNORECASE):
            v.append(f"DIAGNOSIS: {p[:40]}")
    for p in DOSING_RE:
        if re.search(p, text, re.IGNORECASE):
            v.append(f"DOSING: {p[:40]}")
    return v


def _safe_fallback() -> ReasoningOutput:
    return ReasoningOutput(
        patient_response_text=(
            "I'm having difficulty processing your message right now. "
            "If this is urgent, please contact emergency services or your "
            "healthcare provider immediately. " + EMERGENCY_DISCLAIMER
        ),
        clinician_layer=ClinicianLayer(
            summary="System error — response parsing failed.",
            key_findings=[],
            differential_considerations=[],
            working_diagnosis_areas=[],
            risk_flags=[],
            followup_questions=[],
            recommended_physician_actions=["Review session manually — AI response failed."],
            confidence_level="low",
        ),
        safety=SafetyDecision(
            should_escalate=True,
            requires_physician_review=True,
            emergency_detected=False,
            escalation_reason="AI response parsing failure.",
        ),
    )


async def validate_and_enforce(raw_json: str, repair_llm_caller) -> ReasoningOutput:
    try:
        output = ReasoningOutput(**json.loads(raw_json))
    except Exception:
        try:
            repair_sys = (PROMPTS_DIR / "system_repair.txt").read_text()
            repaired = await repair_llm_caller(repair_sys, raw_json)
            output = ReasoningOutput(**json.loads(repaired))
        except Exception:
            return _safe_fallback()

    viol = _violations(output.patient_response_text)
    if viol:
        output.clinician_layer.recommended_physician_actions.append(
            f"CONTENT VIOLATION removed from patient response: {'; '.join(viol)}"
        )
        output.patient_response_text = (
            "Based on what you've described, I want to make sure you get the right care. "
            "Your symptoms are worth discussing with a doctor who can properly evaluate you. "
        )

    emergency_types = {"chest_pain", "suicidality", "severe_breathing", "anaphylaxis", "stroke"}
    high_flags = [f for f in output.clinician_layer.risk_flags if f.severity == "high"]
    emergency = any(f.type in emergency_types for f in high_flags)

    if emergency:
        output.patient_response_text = EMERGENCY_DISCLAIMER + "\n\n" + output.patient_response_text
        output.safety.emergency_detected = True
    elif output.clinician_layer.risk_flags:
        if STANDARD_DISCLAIMER not in output.patient_response_text:
            output.patient_response_text += "\n\n" + STANDARD_DISCLAIMER

    if high_flags:
        output.safety.should_escalate = True
        output.safety.requires_physician_review = True
        if not output.safety.escalation_reason:
            output.safety.escalation_reason = "; ".join(f.type for f in high_flags)

    return output
