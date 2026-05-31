"""Tests for consultation mode and model routing."""

from app.agents.routing import route
from app.schemas import ClinicalContext, PatientProfile, SessionMeta, Turn


def _ctx(text, summary="", user_type="patient", mode="triage"):
    return ClinicalContext(
        patient_profile=PatientProfile(),
        session_meta=SessionMeta(
            session_id="s1",
            channel="text",
            mode=mode,
            user_type=user_type,
        ),
        rolling_summary=summary,
        recent_turns=[],
        current_input=Turn(sender="patient", text=text),
    )


def test_education_routing():
    mode, model = route(_ctx("What is hypertension and how does it develop?"))
    assert mode == "education"
    assert model == "deepseek"


def test_triage_high_risk():
    mode, model = route(_ctx("I have chest pain radiating to my arm"))
    assert mode == "triage"
    assert model == "deepseek"


def test_high_risk_in_summary():
    mode, model = route(_ctx("It happened again", summary="Patient reported chest pain earlier"))
    assert mode == "triage"


def test_default_triage():
    mode, model = route(_ctx("I have a headache"))
    assert mode == "triage"
    assert model == "deepseek"


def test_surgeon_routing_deepseek_only():
    mode, model = route(_ctx("What is the bleeding risk?", user_type="surgeon"))
    assert mode == "surgical"
    assert model == "deepseek"


def test_review_mode_deepseek_only():
    mode, model = route(_ctx("Review this case", mode="review"))
    assert mode == "review"
    assert model == "deepseek"


def test_surgeon_routing_claude_when_enabled(monkeypatch):
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    mode, model = route(_ctx("What is the bleeding risk?", user_type="surgeon"))
    assert mode == "surgical"
    assert model == "claude"


def test_review_mode_claude_when_enabled(monkeypatch):
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    mode, model = route(_ctx("Review this case", mode="review"))
    assert mode == "review"
    assert model == "claude"
