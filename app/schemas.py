"""Pydantic request/response and domain schemas for the consultation API."""

from typing import List, Literal, Optional

from pydantic import BaseModel


class PatientProfile(BaseModel):
    age: Optional[int] = None
    sex: Optional[str] = None
    known_conditions_summary: str = ""
    medications_summary: str = ""
    allergies_summary: str = ""


class SessionMeta(BaseModel):
    session_id: str
    channel: Literal["text", "voice"]
    language: str = "en"
    mode: Literal["triage", "education", "review", "surgical"]
    user_type: Literal["patient", "physician", "surgeon"]


class Turn(BaseModel):
    sender: Literal["patient", "ai", "physician", "surgeon"]
    text: str


class ClinicalContext(BaseModel):
    """The only input the LLM ever receives. Never the full history."""

    patient_profile: PatientProfile
    session_meta: SessionMeta
    rolling_summary: str
    recent_turns: List[Turn]
    current_input: Turn


class RiskFlag(BaseModel):
    type: str
    severity: Literal["low", "medium", "high"]
    rationale: str


class ClinicianLayer(BaseModel):
    """Never shown to patient."""

    summary: str
    key_findings: List[str]
    differential_considerations: List[str]
    working_diagnosis_areas: List[str]
    risk_flags: List[RiskFlag]
    followup_questions: List[str]
    recommended_physician_actions: List[str]
    confidence_level: Literal["low", "medium", "high"]


class SafetyDecision(BaseModel):
    should_escalate: bool
    escalation_reason: Optional[str] = None
    requires_physician_review: bool
    emergency_detected: bool = False


class ReasoningOutput(BaseModel):
    """Fixed schema. LLM must return exactly this structure."""

    patient_response_text: str
    clinician_layer: ClinicianLayer
    safety: SafetyDecision


class TurnRequest(BaseModel):
    session_id: str
    text: str
    channel: Literal["text", "voice"] = "text"
    user_id: str


class TurnResponse(BaseModel):
    patient_response_text: str
    ui_hints: dict = {}
    session_id: str


class CreateSessionRequest(BaseModel):
    patient_id: str
    channel: Literal["text", "voice"] = "text"
    user_type: Literal["patient", "physician", "surgeon"] = "patient"
    mode: Literal["triage", "education", "review", "surgical"] = "triage"


class OverrideRequest(BaseModel):
    text: str


class SurgicalContext(BaseModel):
    procedure_type: str
    phase: Literal["pre_op", "intra_op", "post_op"]
    patient_profile: PatientProfile
    operative_notes: str = ""
    current_alerts: List[str] = []


class SurgeonRequest(BaseModel):
    surgeon_id: str
    surgical_context: SurgicalContext
    query: str


class SurgeonResponse(BaseModel):
    response_text: str
    action_items: List[str]
    risk_flags: List[RiskFlag]
    confidence: Literal["low", "medium", "high"]
