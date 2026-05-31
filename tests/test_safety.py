"""Tests for post-LLM safety validation and content enforcement."""

import json

import pytest

from app.agents.safety import (
    EMERGENCY_DISCLAIMER,
    OFF_TOPIC_REDIRECT,
    STANDARD_DISCLAIMER,
    SOURCE_RESERVE_TOKENS,
    _safe_fallback,
    _violations,
    apply_off_topic_guardrail,
    build_session_context,
    effective_patient_text_cap,
    enforce_patient_text_length,
    ends_with_complete_sentence,
    estimate_tokens,
    has_inline_source,
    has_medical_relevance,
    is_off_topic_model_response,
    is_off_topic_user_message,
    looks_truncated,
    trim_to_last_sentence,
    validate_and_enforce,
)
from tests.conftest import make_reasoning_json


@pytest.mark.asyncio
async def test_citations_preserved_with_disclaimer():
    patient_text = (
        "Persistent headaches can have many causes (Source: NHS — headache guidance). "
        "Tell me more about when this started."
    )
    raw = make_reasoning_json(
        patient_text,
        risk_flags=[{"type": "headache", "severity": "medium", "rationale": "persistent"}],
        source_citations=["NHS — headache guidance"],
    )
    out = await validate_and_enforce(raw, _noop_repair)
    assert STANDARD_DISCLAIMER in out.patient_response_text
    assert "NHS — headache guidance" in out.patient_response_text
    assert out.source_citations == ["NHS — headache guidance"]


@pytest.mark.asyncio
async def test_emergency_disclaimer_with_citations():
    patient_text = (
        "Chest pain with arm radiation needs urgent evaluation "
        "(Source: AHA — heart attack signs)."
    )
    raw = make_reasoning_json(
        patient_text,
        risk_flags=[{"type": "chest_pain", "severity": "high", "rationale": "ACS concern"}],
        source_citations=["AHA — heart attack signs"],
    )
    out = await validate_and_enforce(raw, _noop_repair)
    assert out.patient_response_text.startswith(EMERGENCY_DISCLAIMER)
    assert out.source_citations == ["AHA — heart attack signs"]


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


def test_estimate_tokens_and_sentence_helpers():
    text = "One two three four five."
    assert estimate_tokens(text) == pytest.approx(5 * 1.3)
    assert ends_with_complete_sentence(text)
    assert not looks_truncated(text, 150)
    long = " ".join(["word"] * 200) + " cut off mid"
    assert looks_truncated(long, 50)
    trimmed = trim_to_last_sentence("First sentence. Second runs on without end")
    assert trimmed == "First sentence."


def test_enforce_patient_text_length_trims_at_sentence():
    body = " ".join(["Symptom"] * 80) + ". " + " ".join(["Detail"] * 80) + " trailing without punct"
    out = enforce_patient_text_length(body, max_tokens=40)
    assert estimate_tokens(out) <= 40 + 5
    assert ends_with_complete_sentence(out)


@pytest.mark.asyncio
async def test_validate_enforces_length_on_overlong_patient_text(monkeypatch):
    monkeypatch.setenv("PATIENT_RESPONSE_MAX_TOKENS", "150")
    ramble = " ".join(["Please describe your symptoms in more detail today"] * 30)
    raw = make_reasoning_json(ramble + " and then the model stopped mid-thought with no")
    out = await validate_and_enforce(raw, _noop_repair)
    assert estimate_tokens(out.patient_response_text) <= 150
    assert ends_with_complete_sentence(out.patient_response_text)


@pytest.mark.asyncio
async def test_disclaimer_counts_toward_patient_token_cap():
    """Body + appended STANDARD_DISCLAIMER must stay within PATIENT_RESPONSE_MAX_TOKENS."""
    body = (
        "Thanks for the details. A light, all-over headache that comes and goes in seconds "
        "to minutes, with no other symptoms, is less concerning for serious causes like "
        "stroke or meningitis. It could be something like tension-type headache or even a "
        "benign ice-pick headache (Source: NHS — headache types). Since you're 99, it's "
        "still wise to have it checked by your doctor to rule out any age-related issues "
        "like blood pressure changes. For now, keep a diary of when it happens and what "
        "you're doing. If it gets worse or you develop new symptoms like weakness or "
        "confusion, seek emergency care. Does the headache ever wake you from sleep?"
    )
    raw = make_reasoning_json(
        body,
        source_citations=["NHS — headache types"],
        risk_flags=[{"type": "headache", "severity": "medium", "rationale": "age 99"}],
    )
    out = await validate_and_enforce(raw, _noop_repair)
    assert STANDARD_DISCLAIMER in out.patient_response_text
    assert estimate_tokens(out.patient_response_text) <= 150
    assert ends_with_complete_sentence(out.patient_response_text.split(STANDARD_DISCLAIMER)[0])


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


def test_has_medical_relevance_soccer_injury():
    assert has_medical_relevance("I hurt my knee playing soccer")
    assert not is_off_topic_user_message("I hurt my knee playing soccer")


def test_off_topic_user_world_cup():
    assert is_off_topic_user_message("Who won the world cup in 2022?")
    assert is_off_topic_user_message("tell me about Napoleon Bonaparte")


def test_off_topic_model_response_detected():
    trivia = "Argentina won the 2022 world cup final against France."
    assert is_off_topic_model_response(trivia)
    assert not is_off_topic_model_response("Rest and ice may help a knee injury.")


def test_apply_off_topic_guardrail_replaces_response():
    from app.schemas import ClinicianLayer, ReasoningOutput, SafetyDecision

    output = ReasoningOutput(
        patient_response_text="Brazil won five world cups and Pelé is a legend.",
        clinician_layer=ClinicianLayer(
            summary="Off-topic.",
            key_findings=[],
            differential_considerations=[],
            working_diagnosis_areas=[],
            risk_flags=[],
            followup_questions=[],
            recommended_physician_actions=[],
            confidence_level="low",
        ),
        safety=SafetyDecision(
            should_escalate=False,
            requires_physician_review=False,
        ),
    )
    result = apply_off_topic_guardrail(
        output,
        user_message="Who won the world cup?",
    )
    assert result.safety.off_topic_detected is True
    assert "world cup" not in result.patient_response_text.lower()
    assert result.patient_response_text == OFF_TOPIC_REDIRECT
    assert ends_with_complete_sentence(result.patient_response_text)


@pytest.mark.asyncio
async def test_validate_off_topic_user_redirect():
    raw = make_reasoning_json(
        "Argentina won the 2022 world cup with Messi leading the team."
    )
    out = await validate_and_enforce(
        raw,
        _noop_repair,
        user_message="Who won the world cup?",
    )
    assert out.safety.off_topic_detected is True
    assert "world cup" not in out.patient_response_text.lower()
    assert "napoleon" not in out.patient_response_text.lower()
    assert ends_with_complete_sentence(out.patient_response_text)
    assert estimate_tokens(out.patient_response_text) <= 150


@pytest.mark.asyncio
async def test_validate_medical_soccer_injury_allowed():
    raw = make_reasoning_json(
        "Knee pain after sport often improves with rest and ice. "
        "When did the injury happen and can you bear weight?"
    )
    out = await validate_and_enforce(
        raw,
        _noop_repair,
        user_message="I hurt my knee playing soccer",
    )
    assert not out.safety.off_topic_detected
    assert "knee" in out.patient_response_text.lower()


@pytest.mark.asyncio
async def test_off_topic_redirect_respects_token_cap(monkeypatch):
    monkeypatch.setenv("PATIENT_RESPONSE_MAX_TOKENS", "150")
    raw = make_reasoning_json("Some long off-topic sports trivia answer about finals.")
    out = await validate_and_enforce(
        raw,
        _noop_repair,
        user_message="Who won the super bowl last year?",
    )
    assert out.safety.off_topic_detected is True
    assert estimate_tokens(out.patient_response_text) <= 150
    assert ends_with_complete_sentence(out.patient_response_text)


def test_build_session_context_joins_summary_and_turns():
    from app.schemas import Turn

    ctx = build_session_context(
        "Headache for two days.",
        [Turn(sender="patient", text="It gets worse at night.")],
    )
    assert "Headache" in ctx
    assert "worse at night" in ctx


def test_user_example_paragraph_token_counts():
    """Exact token math for the reported overlong patient paragraph."""
    text = (
        "Thank you for those details. Headaches that come suddenly and then disappear, "
        "even if mild, can have several causes. Since you've had them for a long time and "
        "they're not severe, tension-type headaches or migraines without aura are possible. "
        "However, sudden-onset headaches that resolve quickly can also be a feature of "
        "trigeminal autonomic cephalalgias or even transient ischemic attacks in older adults. "
        "Given your age, it's important to rule out vascular causes. I recommend you see your "
        "primary care doctor for a thorough evaluation, including a neurological exam. They may "
        "consider imaging to be safe. Do you notice any pattern—like time of day or triggers? "
        "This information is not a substitute for professional medical advice. Please consult "
        "your doctor for a proper evaluation."
    )
    disclaimer_start = text.find("This information is not")
    body_only = text[:disclaimer_start].strip()

    assert len(text.split()) == 123
    assert estimate_tokens(text) == pytest.approx(123 * 1.3)
    assert estimate_tokens(text) > 150

    assert len(body_only.split()) == 105
    assert estimate_tokens(body_only) == pytest.approx(105 * 1.3)
    assert estimate_tokens(body_only) <= 150

    combined = body_only + "\n\n" + STANDARD_DISCLAIMER
    assert estimate_tokens(combined) > 150


def test_effective_cap_reserves_source_budget():
    from app.schemas import RiskFlag

    flags = [RiskFlag(type="headache", severity="medium", rationale="x")]
    base = effective_patient_text_cap("Short body.", flags, 150)
    with_source = effective_patient_text_cap(
        "Body (Source: NHS — headaches).",
        flags,
        150,
        source_citations=["NHS — headaches"],
    )
    assert with_source < base
    assert base - with_source == SOURCE_RESERVE_TOKENS


def test_enforce_preserves_inline_source_when_trimming():
    cite = "(Source: NHS — headache types)"
    fluff = " ".join(["Extra clinical detail sentence here."] * 12)
    body = (
        f"Thanks for sharing. Sudden headaches can have many causes {cite}. "
        f"{fluff} Does anything trigger them?"
    )
    from app.schemas import RiskFlag

    flags = [RiskFlag(type="headache", severity="medium", rationale="x")]
    cap = effective_patient_text_cap(body, flags, 150, ["NHS — headache types"])
    out = enforce_patient_text_length(body, cap, source_citations=["NHS — headache types"])
    assert has_inline_source(out)
    assert "NHS — headache types" in out
    assert estimate_tokens(out) <= cap + 2


@pytest.mark.asyncio
async def test_response_with_source_fits_150_token_cap():
    body = (
        "Thanks for the details. Brief headaches that come and go are often tension-type "
        "or migraine (Source: NHS — headache types). At your age, a GP check is wise. "
        "Any pattern with time of day?"
    )
    raw = make_reasoning_json(
        body,
        source_citations=["NHS — headache types"],
        risk_flags=[{"type": "headache", "severity": "medium", "rationale": "persistent"}],
    )
    out = await validate_and_enforce(raw, _noop_repair)
    assert has_inline_source(out.patient_response_text)
    assert out.source_citations == ["NHS — headache types"]
    assert estimate_tokens(out.patient_response_text) <= 150


@pytest.mark.asyncio
async def test_long_text_without_source_gets_trimmed():
    ramble = (
        "Thank you for those details. Headaches that come suddenly and then disappear, "
        "even if mild, can have several causes. Since you've had them for a long time and "
        "they're not severe, tension-type headaches or migraines without aura are possible. "
        "However, sudden-onset headaches that resolve quickly can also be a feature of "
        "trigeminal autonomic cephalalgias or even transient ischemic attacks in older adults. "
        "Given your age, it's important to rule out vascular causes. I recommend you see your "
        "primary care doctor for a thorough evaluation, including a neurological exam. They may "
        "consider imaging to be safe. Do you notice any pattern—like time of day or triggers?"
    )
    raw = make_reasoning_json(
        ramble,
        risk_flags=[{"type": "headache", "severity": "medium", "rationale": "age"}],
    )
    out = await validate_and_enforce(raw, _noop_repair)
    assert not has_inline_source(out.patient_response_text)
    assert estimate_tokens(out.patient_response_text) <= 150
    assert ends_with_complete_sentence(out.patient_response_text.split(STANDARD_DISCLAIMER)[0])


@pytest.mark.asyncio
async def test_source_citations_appended_when_inline_missing():
    body = (
        "Brief headaches at your age deserve a GP review. Any weakness or vision changes?"
    )
    raw = make_reasoning_json(
        body,
        source_citations=["NHS — headache red flags"],
        risk_flags=[{"type": "headache", "severity": "medium", "rationale": "x"}],
    )
    out = await validate_and_enforce(raw, _noop_repair)
    assert has_inline_source(out.patient_response_text)
    assert "NHS — headache red flags" in out.patient_response_text
    assert estimate_tokens(out.patient_response_text) <= 150
