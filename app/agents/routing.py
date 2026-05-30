"""Consultation mode and model routing from clinical context signals."""

from typing import Literal

from app.agents.reasoning import is_claude_enabled
from app.schemas import ClinicalContext

ModelChoice = Literal["deepseek", "claude"]
ModeChoice = Literal["triage", "education", "review", "surgical"]

HIGH_RISK_KW = [
    "suicide",
    "kill myself",
    "end my life",
    "want to die",
    "overdose",
    "chest pain",
    "heart attack",
    "cannot breathe",
    "can't breathe",
    "shortness of breath",
    "stroke",
    "seizure",
    "unconscious",
    "not waking",
    "bleeding heavily",
    "anaphylaxis",
    "severe allergic",
    "collapsed",
    "unresponsive",
]
EDUCATION_KW = [
    "what is",
    "explain",
    "how does",
    "tell me about",
    "what are symptoms",
    "what causes",
    "difference between",
    "is it normal",
    "what should i know",
    "how do i know",
    "what happens",
]


def route(ctx: ClinicalContext) -> tuple[ModeChoice, ModelChoice]:
    text = ctx.current_input.text.lower()
    summary = ctx.rolling_summary.lower()

    if ctx.session_meta.user_type == "surgeon":
        return "surgical", "claude" if is_claude_enabled() else "deepseek"
    if ctx.session_meta.mode == "review":
        return "review", "claude" if is_claude_enabled() else "deepseek"
    for kw in HIGH_RISK_KW:
        if kw in text or kw in summary:
            return "triage", "deepseek"
    for kw in EDUCATION_KW:
        if kw in text:
            return "education", "deepseek"
    return "triage", "deepseek"
