"""Post-LLM safety validation, content enforcement, and structured fallback."""

import json
import os
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
EMERGENCY_TYPES = frozenset(
    {"chest_pain", "suicidality", "severe_breathing", "anaphylaxis", "stroke"}
)
INLINE_SOURCE_RE = re.compile(r"\(Source:\s*[^)]+\)", re.IGNORECASE)
SOURCE_RESERVE_TOKENS = 18
OFF_TOPIC_REDIRECT = (
    "I'm here for health and medical questions only, so I can't help with that topic. "
    "What symptoms or health concerns would you like to discuss today?"
)

MEDICAL_MARKERS_RE = [
    r"\b(pain|hurt|injur(?:y|ed)|symptom|ache|aching|sore|swell|bleed|fever|cough|nausea)\b",
    r"\b(medication|medicine|meds|dose|allerg|prescri|doctor|hospital|diagnos|treatment|therapy)\b",
    r"\b(headache|chest|breath|dizz|vomit|rash|anxiety|depress|suicid|sleep|fatigue|weakness)\b",
    r"\b(knee|ankle|back|stomach|throat|heart|skin|arm|leg|neck|shoulder|hip|wrist)\b",
    r"\b(infection|virus|bacteria|chronic|acute|condition|illness|disease|health)\b",
    r"\b(pregnant|pregnancy|childbirth|menstr|period|contracep)\b",
]

OFF_TOPIC_USER_RE = [
    r"\bwho won\b",
    r"\bworld cup\b",
    r"\bsuper bowl\b",
    r"\b(champion(?:ship)?|final score|match result)\b",
    r"\btell me about\b.{0,60}\b(napoleon|hitler|caesar|president|emperor|dynasty|war)\b",
    r"\b(recipe|cooking|restaurant|movie|film|song|album|celebrity|netflix)\b",
    r"\b(weather forecast|stock market|crypto|bitcoin|ethereum)\b",
    r"\b(tell|write|make)\b.{0,25}\b(joke|riddle|poem|story)\b",
    r"\bwhat(?:'s| is) (?:the )?(?:capital|population) of\b",
    r"\bplay(?:ing)?\s+(?:for|in)\s+\w+\s+(?:fc|team|club)\b",
]

OFF_TOPIC_RESPONSE_RE = [
    r"\bwon the\b.{0,40}\b(world cup|championship|super bowl|final)\b",
    r"\b(napoleon|bonaparte)\b.{0,50}\b(born|died|emperor|battle|france)\b",
    r"\bfinal score\b.{0,30}\b\d+\s*[-–]\s*\d+\b",
    r"\b(released in|directed by|starring)\b.{0,30}\b(film|movie|series)\b",
]


def patient_text_max_tokens() -> int:
    """Default cap for patient-visible prose including appended system disclaimers."""
    return int(os.getenv("PATIENT_RESPONSE_MAX_TOKENS", "150"))


def _disclaimer_reserve_tokens(patient_text: str, risk_flags) -> int:
    """Reserve token budget for disclaimers appended after length enforcement."""
    high_flags = [f for f in risk_flags if f.severity == "high"]
    emergency = any(f.type in EMERGENCY_TYPES for f in high_flags)
    if emergency:
        return int(estimate_tokens(EMERGENCY_DISCLAIMER + "\n\n")) + 1
    if risk_flags and STANDARD_DISCLAIMER not in patient_text:
        return int(estimate_tokens("\n\n" + STANDARD_DISCLAIMER)) + 1
    return 0


def has_inline_source(text: str) -> bool:
    return bool(INLINE_SOURCE_RE.search(text or ""))


def _source_reserve_tokens(patient_text: str, source_citations: list[str] | None) -> int:
    """Reserve budget for one compact inline source when citations apply."""
    if has_inline_source(patient_text) or source_citations:
        return SOURCE_RESERVE_TOKENS
    return 0


def effective_patient_text_cap(
    patient_text: str,
    risk_flags,
    max_tokens: int | None = None,
    source_citations: list[str] | None = None,
) -> int:
    """Body token cap so final patient text (with disclaimers) stays within max_tokens."""
    cap = max_tokens if max_tokens is not None else patient_text_max_tokens()
    reserve = _disclaimer_reserve_tokens(patient_text, risk_flags)
    reserve += _source_reserve_tokens(patient_text, source_citations)
    return max(40, cap - reserve)


def _split_sentences(text: str) -> list[str]:
    """Split prose into sentence chunks, keeping trailing punctuation on each chunk."""
    parts: list[str] = []
    start = 0
    for m in re.finditer(r"[.?!]", text):
        chunk = text[start : m.end()].strip()
        if chunk:
            parts.append(chunk)
        start = m.end()
    tail = text[start:].strip()
    if tail:
        parts.append(tail)
    return parts if parts else [text.strip()]


def _join_sentences(sentences: list[str]) -> str:
    return " ".join(s.strip() for s in sentences if s.strip()).strip()


def _ensure_inline_citation(text: str, source_citations: list[str] | None) -> str:
    """Append a compact inline cite when source_citations exist but prose has none."""
    if not source_citations or has_inline_source(text):
        return text.strip()
    cite = f"(Source: {source_citations[0]})"
    t = text.rstrip()
    if not t:
        return cite
    if t[-1] in ".?!":
        return f"{t} {cite}"
    return f"{t}. {cite}"


def _trim_sentences_preserving_sources(sentences: list[str], cap: float) -> list[str]:
    """Drop non-source sentences from the end until text fits; never remove source sentences."""
    kept = list(sentences)
    while kept and estimate_tokens(_join_sentences(kept)) > cap:
        removed = False
        for i in range(len(kept) - 1, -1, -1):
            if not has_inline_source(kept[i]):
                kept.pop(i)
                removed = True
                break
        if not removed:
            break
    return kept


def estimate_tokens(text: str) -> float:
    words = text.split()
    if not words:
        return 0.0
    return len(words) * 1.3


def ends_with_complete_sentence(text: str) -> bool:
    t = text.rstrip()
    return bool(t) and t[-1] in ".?!"


def looks_truncated(text: str, max_tokens: int) -> bool:
    if ends_with_complete_sentence(text):
        return False
    est = estimate_tokens(text)
    if est >= max_tokens * 0.85:
        return True
    stripped = text.rstrip()
    return bool(stripped) and stripped[-1].isalnum() and est >= max_tokens * 0.5


def trim_to_last_sentence(text: str) -> str:
    t = text.rstrip()
    if not t:
        return t
    last_end = -1
    for m in re.finditer(r"[.?!]", t):
        last_end = m.end()
    if last_end > 0:
        return t[:last_end].rstrip()
    return t


def enforce_patient_text_length(
    text: str,
    max_tokens: int | None = None,
    *,
    source_citations: list[str] | None = None,
) -> str:
    """Trim or close patient prose to fit token budget without mid-sentence cutoffs."""
    cap = max_tokens if max_tokens is not None else patient_text_max_tokens()
    out = text.strip()
    if not out:
        return out

    protect_sources = has_inline_source(out) or bool(source_citations)

    if protect_sources and estimate_tokens(out) > cap:
        sentences = _split_sentences(out)
        kept = _trim_sentences_preserving_sources(sentences, cap)
        out = _join_sentences(kept)

    while estimate_tokens(out) > cap and len(out) > 24:
        if protect_sources:
            sentences = _split_sentences(out)
            if len(sentences) > 1:
                kept = _trim_sentences_preserving_sources(sentences, cap)
                if _join_sentences(kept) != out:
                    out = _join_sentences(kept)
                    continue
        trimmed = trim_to_last_sentence(out)
        if protect_sources and trimmed and not has_inline_source(trimmed):
            sentences = _split_sentences(out)
            kept = _trim_sentences_preserving_sources(sentences, cap)
            candidate = _join_sentences(kept)
            if candidate and has_inline_source(candidate):
                out = candidate
                continue
        if not trimmed or trimmed == out:
            if protect_sources:
                sources = INLINE_SOURCE_RE.findall(out)
                body = INLINE_SOURCE_RE.sub("", out).strip()
                source_cost = sum(estimate_tokens(s) for s in sources) + max(0, len(sources) - 1)
                body_cap = max(20, cap - source_cost)
                words = body.split()
                while words and estimate_tokens(" ".join(words)) > body_cap:
                    words.pop()
                body = " ".join(words).rstrip(".,;:")
                if body and not ends_with_complete_sentence(body):
                    body += "."
                out = f"{body} {' '.join(sources)}".strip() if sources else body
            else:
                words = out.split()
                while words and estimate_tokens(" ".join(words)) > cap:
                    words.pop()
                out = " ".join(words).rstrip(".,;:")
                if out and not ends_with_complete_sentence(out):
                    out += "."
            continue
        out = trimmed

    if looks_truncated(out, cap):
        trimmed = trim_to_last_sentence(out)
        if trimmed and (not protect_sources or has_inline_source(trimmed)):
            out = trimmed
        elif out and not ends_with_complete_sentence(out):
            out = out.rstrip(".,;:") + "."

    return out


def _violations(text: str) -> list[str]:
    v = []
    for p in DIAGNOSIS_RE:
        if re.search(p, text, re.IGNORECASE):
            v.append(f"DIAGNOSIS: {p[:40]}")
    for p in DOSING_RE:
        if re.search(p, text, re.IGNORECASE):
            v.append(f"DOSING: {p[:40]}")
    return v


def has_medical_relevance(text: str) -> bool:
    if not text or not text.strip():
        return False
    for pattern in MEDICAL_MARKERS_RE:
        if re.search(pattern, text, re.IGNORECASE):
            return True
    return False


def is_off_topic_user_message(message: str, session_context: str = "") -> bool:
    """True when the patient turn is clearly non-medical with no medical tie-in."""
    msg = (message or "").strip()
    if not msg:
        return False
    if has_medical_relevance(msg):
        return False
    for pattern in OFF_TOPIC_USER_RE:
        if re.search(pattern, msg, re.IGNORECASE):
            return True
    return False


def is_off_topic_model_response(text: str) -> bool:
    """True when patient_response_text answers a non-medical trivia-style question."""
    if not text or not text.strip():
        return False
    if has_medical_relevance(text):
        return False
    for pattern in OFF_TOPIC_RESPONSE_RE:
        if re.search(pattern, text, re.IGNORECASE):
            return True
    return False


def build_session_context(rolling_summary: str = "", recent_turns=None) -> str:
    parts = [rolling_summary or ""]
    for turn in recent_turns or []:
        parts.append(getattr(turn, "text", str(turn)))
    return " ".join(p for p in parts if p).strip()


def apply_off_topic_guardrail(
    output: ReasoningOutput,
    user_message: str | None = None,
    session_context: str = "",
    max_tokens: int | None = None,
) -> ReasoningOutput:
    """Replace patient text with redirect when user or model output is clearly off-topic."""
    cap = max_tokens if max_tokens is not None else patient_text_max_tokens()
    user_off_topic = bool(user_message) and is_off_topic_user_message(user_message, session_context)
    response_off_topic = is_off_topic_model_response(output.patient_response_text)

    if not user_off_topic and not response_off_topic:
        return output

    output.patient_response_text = enforce_patient_text_length(OFF_TOPIC_REDIRECT, cap)
    output.safety.off_topic_detected = True
    output.clinician_layer.recommended_physician_actions.append(
        "SCOPE: off-topic request redirected to medical consultation."
    )
    return output


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


async def validate_and_enforce(
    raw_json: str,
    repair_llm_caller,
    *,
    user_message: str | None = None,
    session_context: str = "",
    max_tokens: int | None = None,
) -> ReasoningOutput:
    try:
        output = ReasoningOutput(**json.loads(raw_json))
    except Exception:
        try:
            repair_sys = (PROMPTS_DIR / "system_repair.txt").read_text()
            repaired = await repair_llm_caller(repair_sys, raw_json)
            output = ReasoningOutput(**json.loads(repaired))
        except Exception:
            return _safe_fallback()

    cap = max_tokens if max_tokens is not None else patient_text_max_tokens()
    output = apply_off_topic_guardrail(output, user_message, session_context, cap)
    output.patient_response_text = _ensure_inline_citation(
        output.patient_response_text, output.source_citations
    )
    body_cap = effective_patient_text_cap(
        output.patient_response_text,
        output.clinician_layer.risk_flags,
        cap,
        output.source_citations,
    )
    output.patient_response_text = enforce_patient_text_length(
        output.patient_response_text,
        body_cap,
        source_citations=output.source_citations,
    )

    viol = _violations(output.patient_response_text)
    if viol:
        output.clinician_layer.recommended_physician_actions.append(
            f"CONTENT VIOLATION removed from patient response: {'; '.join(viol)}"
        )
        output.patient_response_text = (
            "Based on what you've described, I want to make sure you get the right care. "
            "Your symptoms are worth discussing with a doctor who can properly evaluate you. "
        )

    high_flags = [f for f in output.clinician_layer.risk_flags if f.severity == "high"]
    emergency = any(f.type in EMERGENCY_TYPES for f in high_flags)

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
