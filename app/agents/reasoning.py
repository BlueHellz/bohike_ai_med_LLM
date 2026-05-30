"""LLM invocation and clinical reasoning orchestration."""

import json
import os
from pathlib import Path
from typing import Callable, Optional

from app.schemas import ClinicalContext, ReasoningOutput, SurgicalContext

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
    """Dependency injection for tests."""
    global _deepseek_caller, _claude_caller
    _deepseek_caller = deepseek_fn
    _claude_caller = claude_fn


def reset_llm_callers() -> None:
    set_llm_callers(None, None)


async def call_deepseek(system, user, max_tokens=900):
    if _deepseek_caller:
        return await _deepseek_caller(system, user, max_tokens=max_tokens)
    if _mock_enabled():
        raise RuntimeError("MOCK_LLM enabled but no deepseek caller injected")
    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=os.getenv("DEEPSEEK_API_KEY"), base_url=DS_BASE)
    r = await client.chat.completions.create(
        model=DS_MODEL,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        max_tokens=max_tokens,
        temperature=0.2,
        response_format={"type": "json_object"},
    )
    return r.choices[0].message.content


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


def _build_system(mode):
    tmpl = (PROMPTS_DIR / "system_patient.txt").read_text()
    return tmpl.format(
        mode=mode,
        patient_max=P_MAX,
        clinician_max=C_MAX,
        schema_json=json.dumps(SCHEMA, indent=2),
    )


def _validate_reasoning_json(raw: str) -> None:
    data = json.loads(raw)
    assert "patient_response_text" in data
    assert "clinician_layer" in data
    assert "safety" in data
    assert data["clinician_layer"].get("confidence_level") in ("low", "medium", "high")


async def run_reasoning(ctx: ClinicalContext, mode: str, model: str) -> tuple[str, bool]:
    """Returns (raw_json, used_claude)."""
    if mode == "review":
        system = (PROMPTS_DIR / "system_review.txt").read_text().format(
            schema_json=json.dumps(SCHEMA, indent=2)
        )
    else:
        system = _build_system(mode)

    user = ctx.model_dump_json()

    if model == "claude" and is_claude_enabled():
        return await call_claude(system, user), True

    raw = await call_deepseek(system, user)

    try:
        _validate_reasoning_json(raw)
        return raw, False
    except Exception:
        if is_claude_enabled():
            raw = await call_claude(system, user)
            return raw, True

        raw = await call_deepseek(system, user)
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
