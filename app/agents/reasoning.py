"""LLM invocation and clinical reasoning orchestration."""

import json
import logging
import os
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Callable, Optional

from app.agents.voice_config import voice_patient_max_tokens, voice_reasoning_max_tokens
from app.llm_errors import LlmConfigurationError, LlmUpstreamError
from app.schemas import ClinicalContext, ReasoningOutput, SurgicalContext

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).resolve().parents[2] / "prompts"

DS_BASE = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
DS_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
CL_MODEL = os.getenv("CLAUDE_MODEL", "claude-opus-4-5")
P_MAX = int(os.getenv("PATIENT_RESPONSE_MAX_TOKENS", "200"))
C_MAX = int(os.getenv("CLINICIAN_SUMMARY_MAX_TOKENS", "250"))
SCHEMA = ReasoningOutput.model_json_schema()

_deepseek_caller: Optional[Callable] = None
_claude_caller: Optional[Callable] = None


def _mock_enabled() -> bool:
    return os.getenv("MOCK_LLM", "").lower() in ("1", "true", "yes")


def _dev_stub_enabled() -> bool:
    return os.getenv("DEV_STUB_LLM", "").lower() in ("1", "true", "yes")


def _deepseek_api_key() -> str:
    return (os.getenv("DEEPSEEK_API_KEY") or "").strip()


def _dev_stub_reasoning_json(user_payload: str) -> str:
    """Return valid ReasoningOutput JSON for local test-ui when no API key is configured."""
    patient_text = (
        "I want to understand your headache better. When did it start, "
        "how severe is it on a scale of 1 to 10, and do you have any other symptoms?"
    )
    source_citations: list[str] = []
    if "headache" in user_payload.lower():
        patient_text = (
            "Thank you for telling me about your headache. Sudden severe headaches "
            "can sometimes signal something urgent (Source: NHS — headache red flags). "
            "I need a few more details to help guide you: when did it start, how severe "
            "is the pain from 1 to 10, and do you have fever, vision changes, or the "
            "worst headache of your life?"
        )
        source_citations = ["NHS — headache red flags"]
    return json.dumps(
        {
            "patient_response_text": patient_text,
            "source_citations": source_citations,
            "clinician_layer": {
                "summary": "Dev stub — headache presentation; gather onset, severity, red flags.",
                "key_findings": ["Headache reported (dev stub)"],
                "differential_considerations": ["Tension-type headache", "Migraine", "Secondary causes"],
                "working_diagnosis_areas": ["Headache"],
                "risk_flags": [],
                "followup_questions": [
                    "Onset and duration?",
                    "Severity 1-10?",
                    "Associated neuro symptoms?",
                ],
                "recommended_physician_actions": [],
                "confidence_level": "low",
            },
            "safety": {
                "should_escalate": False,
                "escalation_reason": None,
                "requires_physician_review": False,
                "emergency_detected": False,
            },
        }
    )


def _dev_stub_summary(user_payload: str) -> str:
    if "headache" in user_payload.lower():
        return (
            "Patient reports headache. Onset, severity, and red-flag symptoms "
            "still being clarified (dev stub summary)."
        )
    return "Consultation in progress (dev stub summary)."


def is_claude_enabled() -> bool:
    """
    Return whether Anthropic Claude may be invoked.

    When ``LLM_PROVIDER=deepseek``, Claude is disabled regardless of API key presence.
    Otherwise Claude is enabled only when ``ANTHROPIC_API_KEY`` is set.
    """
    provider = os.getenv("LLM_PROVIDER", "").lower()
    if provider == "deepseek":
        return False
    return bool(os.getenv("ANTHROPIC_API_KEY"))


def set_llm_callers(deepseek_fn=None, claude_fn=None) -> None:
    """Test-only hooks for injecting mock LLM callers."""
    global _deepseek_caller, _claude_caller
    _deepseek_caller = deepseek_fn
    _claude_caller = claude_fn


def reset_llm_callers() -> None:
    set_llm_callers(None, None)


async def call_deepseek(system, user, max_tokens=900, *, json_mode: bool = True):
    if _deepseek_caller:
        return await _deepseek_caller(system, user, max_tokens=max_tokens)
    if _mock_enabled():
        raise RuntimeError("MOCK_LLM enabled but no deepseek caller injected")
    api_key = _deepseek_api_key()
    if not api_key:
        if _dev_stub_enabled():
            if "EXISTING SUMMARY:" in user:
                return _dev_stub_summary(user)
            return _dev_stub_reasoning_json(user)
        raise LlmConfigurationError(
            "DEEPSEEK_API_KEY is not configured. Set the key in .env or enable DEV_STUB_LLM=true for local test-ui."
        )
    from openai import AsyncOpenAI

    try:
        client = AsyncOpenAI(api_key=api_key, base_url=DS_BASE)
        kwargs = {
            "model": DS_MODEL,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "max_tokens": max_tokens,
            "temperature": 0.2,
        }
        # DeepSeek json_object mode requires the token "json" in the system prompt.
        if json_mode and "json" in system.lower():
            kwargs["response_format"] = {"type": "json_object"}
        r = await client.chat.completions.create(**kwargs)
        return r.choices[0].message.content
    except Exception as exc:
        logger.exception("DeepSeek API call failed")
        raise LlmUpstreamError(str(exc)) from exc


async def call_claude(system, user, max_tokens=900):
    if not is_claude_enabled():
        raise RuntimeError("Claude is disabled (LLM_PROVIDER=deepseek or no ANTHROPIC_API_KEY)")
    if _claude_caller:
        return await _claude_caller(system, user, max_tokens=max_tokens)
    if _mock_enabled():
        raise RuntimeError("MOCK_LLM enabled but no claude caller injected")
    import anthropic

    client = anthropic.AsyncAnthropic()
    msg = await client.messages.create(
        model=CL_MODEL,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    return msg.content[0].text


VOICE_CHANNEL_USER_NOTE = (
    "VOICE_CHANNEL: session_meta.channel is voice. patient_response_text must be "
    "spoken aloud: at most 3 short sentences total, plus 1–2 brief follow-up questions "
    "(not more). Use natural contractions, no long parentheticals, no bullet lists; "
    "warm and clear; same clinical rigor and citation rules as text mode."
)


def _build_user_payload(ctx: ClinicalContext) -> str:
    payload = ctx.model_dump_json()
    if ctx.session_meta.channel == "voice":
        return payload + "\n\n" + VOICE_CHANNEL_USER_NOTE
    return payload


def _build_system(mode, citation_depth="simple", *, patient_max: int | None = None):
    tmpl = (PROMPTS_DIR / "system_patient.txt").read_text()
    return tmpl.format(
        mode=mode,
        citation_depth=citation_depth,
        patient_max=patient_max if patient_max is not None else P_MAX,
        clinician_max=C_MAX,
        schema_json=json.dumps(SCHEMA, indent=2),
    )


def _reasoning_max_tokens(channel: str) -> int:
    if channel == "voice":
        return voice_reasoning_max_tokens()
    return 900


def _patient_max_for_channel(channel: str) -> int:
    if channel == "voice":
        return voice_patient_max_tokens()
    return P_MAX


def _validate_reasoning_json(raw: str) -> None:
    data = json.loads(raw)
    assert "patient_response_text" in data
    assert "clinician_layer" in data
    assert "safety" in data
    assert data["clinician_layer"].get("confidence_level") in ("low", "medium", "high")


async def stream_deepseek(
    system: str, user: str, max_tokens: int = 900, *, json_mode: bool = True
) -> AsyncIterator[str]:
    """Yield DeepSeek completion text deltas (or full body for stubs/injected callers)."""
    if _deepseek_caller:
        full = await _deepseek_caller(system, user, max_tokens=max_tokens)
        yield full
        return
    if _mock_enabled():
        raise RuntimeError("MOCK_LLM enabled but no deepseek caller injected")
    api_key = _deepseek_api_key()
    if not api_key:
        if _dev_stub_enabled():
            if "EXISTING SUMMARY:" in user:
                yield _dev_stub_summary(user)
            else:
                yield _dev_stub_reasoning_json(user)
            return
        raise LlmConfigurationError(
            "DEEPSEEK_API_KEY is not configured. Set the key in .env or enable DEV_STUB_LLM=true for local test-ui."
        )
    from openai import AsyncOpenAI

    try:
        client = AsyncOpenAI(api_key=api_key, base_url=DS_BASE)
        kwargs = {
            "model": DS_MODEL,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "max_tokens": max_tokens,
            "temperature": 0.2,
            "stream": True,
        }
        if json_mode and "json" in system.lower():
            kwargs["response_format"] = {"type": "json_object"}
        stream = await client.chat.completions.create(**kwargs)
        async for chunk in stream:
            delta = chunk.choices[0].delta.content if chunk.choices else None
            if delta:
                yield delta
    except Exception as exc:
        logger.exception("DeepSeek streaming call failed")
        raise LlmUpstreamError(str(exc)) from exc


def build_reasoning_prompts(ctx: ClinicalContext, mode: str) -> tuple[str, str, int]:
    """Return (system, user, max_tokens) for a reasoning call."""
    channel = ctx.session_meta.channel
    max_tokens = _reasoning_max_tokens(channel)
    if mode == "review":
        system = (PROMPTS_DIR / "system_review.txt").read_text().format(
            schema_json=json.dumps(SCHEMA, indent=2)
        )
    else:
        system = _build_system(
            mode,
            ctx.session_meta.citation_depth,
            patient_max=_patient_max_for_channel(channel),
        )
    return system, _build_user_payload(ctx), max_tokens


async def run_reasoning(ctx: ClinicalContext, mode: str, model: str) -> tuple[str, bool]:
    """Return raw reasoning JSON and whether Claude handled the call."""
    system, user, max_tokens = build_reasoning_prompts(ctx, mode)

    if model == "claude" and is_claude_enabled():
        return await call_claude(system, user, max_tokens=max_tokens), True

    raw = await call_deepseek(system, user, max_tokens=max_tokens)

    try:
        _validate_reasoning_json(raw)
        return raw, False
    except Exception:
        if is_claude_enabled():
            raw = await call_claude(system, user, max_tokens=max_tokens)
            return raw, True

        raw = await call_deepseek(system, user, max_tokens=max_tokens)
        try:
            _validate_reasoning_json(raw)
            return raw, False
        except Exception:
            return raw, False


async def run_surgical(ctx: SurgicalContext, query: str) -> str:
    if not is_claude_enabled():
        raise RuntimeError("Surgeon tier requires Claude — not configured")
    system = (PROMPTS_DIR / "system_surgeon.txt").read_text().format(
        phase=ctx.phase, procedure=ctx.procedure_type
    )
    user = f"Context:\n{ctx.model_dump_json()}\n\nSurgeon query: {query}"
    return await call_claude(system, user, max_tokens=600)
