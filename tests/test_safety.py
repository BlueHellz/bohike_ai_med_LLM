import json

import pytest

from app.agents.safety import (
    EMERGENCY_DISCLAIMER,
    STANDARD_DISCLAIMER,
    _safe_fallback,
    _violations,
    validate_and_enforce,
)
from tests.conftest import make_reasoning_json


@pytest.mark.asyncio
async def test_diagnosis_stripped():
    raw = make_reasoning_json("You have diabetes and should monitor your blood sugar.")
    out = await validate_and_enforce(raw, _noop_repair)
    assert "diabetes" not in out.patient_response_text.lower()
    assert "Based on what you've described" in out.patient_response_text
    assert any("CONTENT VIOLATION" in a for a in out.clinician_layer.recommended_physician_actions)


@pytest.mark.asyncio
async def test_dosing_stripped():
    raw = make_reasoning_json("Please take 500mg twice daily with food.")
    out = await validate_and_enforce(raw, _noop_repair)
    assert "500mg" not in out.patient_response_text
    assert "Based on what you've described" in out.patient_response_text


@pytest.mark.asyncio
async def test_high_severity_escalates():
    raw = make_reasoning_json(
        "Please seek urgent care.",
        risk_flags=[{"type": "other", "severity": "high", "rationale": "concerning"}],
    )
    out = await validate_and_enforce(raw, _noop_repair)
    assert out.safety.should_escalate is True
    assert out.safety.requires_physician_review is True


@pytest.mark.asyncio
async def test_emergency_disclaimer_prepended():
    raw = make_reasoning_json(
        "Call emergency services now.",
        risk_flags=[{"type": "chest_pain", "severity": "high", "rationale": "ACS concern"}],
    )
    out = await validate_and_enforce(raw, _noop_repair)
    assert out.patient_response_text.startswith(EMERGENCY_DISCLAIMER)
    assert out.safety.emergency_detected is True


@pytest.mark.asyncio
async def test_medium_flag_adds_standard_disclaimer():
    raw = make_reasoning_json(
        "Monitor your symptoms closely.",
        risk_flags=[{"type": "headache", "severity": "medium", "rationale": "persistent"}],
    )
    out = await validate_and_enforce(raw, _noop_repair)
    assert STANDARD_DISCLAIMER in out.patient_response_text
    assert not out.safety.emergency_detected


@pytest.mark.asyncio
async def test_no_flags_no_disclaimer():
    raw = make_reasoning_json("Tell me more about when this started.")
    out = await validate_and_enforce(raw, _noop_repair)
    assert STANDARD_DISCLAIMER not in out.patient_response_text
    assert EMERGENCY_DISCLAIMER not in out.patient_response_text


@pytest.mark.asyncio
async def test_malformed_json_fallback():
    async def failing_repair(_sys, _raw):
        raise ValueError("repair failed")

    out = await validate_and_enforce("not json at all", failing_repair)
    assert out.safety.should_escalate is True
    assert out.safety.requires_physician_review is True


@pytest.mark.asyncio
async def test_fallback_properties():
    out = _safe_fallback()
    assert out.safety.should_escalate is True
    assert out.safety.requires_physician_review is True


@pytest.mark.asyncio
async def test_clean_response_unchanged():
    text = "Can you describe the pain — when did it start and how severe is it?"
    raw = make_reasoning_json(text)
    out = await validate_and_enforce(raw, _noop_repair)
    assert out.patient_response_text == text
    assert _violations(out.patient_response_text) == []


@pytest.mark.asyncio
async def test_repair_pass_succeeds():
    broken = '{"patient_response_text": "Hello", "clinician_layer": {'
    fixed = make_reasoning_json("Repaired response.")

    async def repair(_sys, _raw):
        return fixed

    out = await validate_and_enforce(broken, repair)
    assert out.patient_response_text == "Repaired response."


async def _noop_repair(_sys, _raw):
    return _raw
