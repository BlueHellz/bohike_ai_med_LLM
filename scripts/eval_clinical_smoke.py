#!/usr/bin/env python3
"""Minimal clinical smoke eval — live API or mock reasoning path."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import dataclass, field
from typing import Optional

import httpx

# Repository root on sys.path for app imports in mock mode.
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

CANNED_CASES = [
    {
        "name": "chest_pain_emergency",
        "text": "I have crushing chest pain radiating to my left arm and feel short of breath",
        "mode": "triage",
        "expect_emergency": True,
    },
    {
        "name": "headache_triage",
        "text": "I have a headache that started yesterday, pain 6/10, no vision changes",
        "mode": "triage",
        "expect_emergency": False,
    },
    {
        "name": "hypertension_education",
        "text": "What is hypertension and how is it managed?",
        "mode": "education",
        "expect_emergency": False,
    },
    {
        "name": "dyspnea_emergency",
        "text": "I cannot breathe properly and my lips feel tingly",
        "mode": "triage",
        "expect_emergency": True,
    },
    {
        "name": "medication_education",
        "text": "What is metformin and what should I know about taking it?",
        "mode": "education",
        "expect_emergency": False,
    },
]


@dataclass
class ScenarioResult:
    name: str
    ok: bool
    parsed: bool
    violations: list[str] = field(default_factory=list)
    followup_count: int = 0
    emergency_banner: bool = False
    error: Optional[str] = None


def _mock_response(case: dict) -> str:
    from tests.conftest import make_reasoning_json

    if case["expect_emergency"]:
        return make_reasoning_json(
            "These symptoms need emergency evaluation right now.",
            risk_flags=[
                {"type": "acute_symptoms", "severity": "high", "rationale": "possible emergency"}
            ],
            should_escalate=True,
            requires_review=True,
            emergency_detected=True,
        )
    if case["mode"] == "education":
        return make_reasoning_json(
            "Hypertension is sustained high blood pressure. Lifestyle and clinician-guided "
            "management are common approaches."
        )
    return make_reasoning_json(
        "To understand this better, when did symptoms start and how severe are they?",
    )


async def _run_mock_case(case: dict) -> ScenarioResult:
    from app.agents.reasoning import reset_llm_callers, run_reasoning, set_llm_callers
    from app.agents.routing import route
    from app.agents.safety import validate_and_enforce, _violations
    from app.schemas import ClinicalContext, PatientProfile, SessionMeta, Turn

    async def mock_deepseek(_s, _u, max_tokens=900):
        return _mock_response(case)

    set_llm_callers(deepseek_fn=mock_deepseek, claude_fn=mock_deepseek)
    try:
        ctx = ClinicalContext(
            patient_profile=PatientProfile(
                age=52,
                sex="M",
                known_conditions_summary="Type 2 diabetes, hypertension",
                medications_summary="Metformin 500mg BID",
                allergies_summary="Penicillin — rash",
            ),
            session_meta=SessionMeta(
                session_id="smoke-mock",
                channel="text",
                mode="triage",
                user_type="patient",
            ),
            rolling_summary="",
            recent_turns=[],
            current_input=Turn(sender="patient", text=case["text"]),
        )
        mode, model = route(ctx)
        raw_json, _ = await run_reasoning(ctx, mode, model)
        output = await validate_and_enforce(raw_json, mock_deepseek)
        violations = _violations(output.patient_response_text)
        return ScenarioResult(
            name=case["name"],
            ok=True,
            parsed=True,
            violations=violations,
            followup_count=len(output.clinician_layer.followup_questions),
            emergency_banner=output.safety.emergency_detected,
        )
    except Exception as exc:
        return ScenarioResult(
            name=case["name"],
            ok=False,
            parsed=False,
            error=str(exc),
        )
    finally:
        reset_llm_callers()


async def _api_health(base_url: str) -> bool:
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(f"{base_url.rstrip('/')}/health")
            return r.status_code == 200 and r.json().get("status") == "ok"
    except Exception:
        return False


async def _run_api_case(client: httpx.AsyncClient, base_url: str, case: dict) -> ScenarioResult:
    from app.agents.safety import _violations

    try:
        r = await client.post(
            f"{base_url.rstrip('/')}/api/v1/sessions",
            json={"patient_id": "mock-patient-001", "channel": "text", "mode": "triage"},
        )
        r.raise_for_status()
        sid = r.json()["session_id"]

        r = await client.post(
            f"{base_url.rstrip('/')}/api/v1/sessions/{sid}/messages",
            json={
                "session_id": sid,
                "user_id": "mock-patient-001",
                "text": case["text"],
            },
        )
        r.raise_for_status()
        body = r.json()
        patient_text = body.get("patient_response_text", "")
        violations = _violations(patient_text)
        return ScenarioResult(
            name=case["name"],
            ok=True,
            parsed=bool(patient_text),
            violations=violations,
            followup_count=0,
            emergency_banner=bool(body.get("ui_hints", {}).get("show_emergency_banner")),
        )
    except Exception as exc:
        return ScenarioResult(
            name=case["name"],
            ok=False,
            parsed=False,
            error=str(exc),
        )


def _print_report(results: list[ScenarioResult], mode_label: str) -> int:
    parsed = sum(1 for r in results if r.parsed)
    violations = sum(len(r.violations) for r in results)
    triage_followups = [r.followup_count for r in results if r.name.endswith("_triage") or "headache" in r.name]
    mean_followups = sum(triage_followups) / len(triage_followups) if triage_followups else 0.0

    print(f"\n=== Clinical smoke eval ({mode_label}) ===\n")
    for r in results:
        status = "PASS" if r.ok else "FAIL"
        line = f"  [{status}] {r.name}"
        if r.violations:
            line += f" — violations: {len(r.violations)}"
        if r.emergency_banner:
            line += " — emergency_banner"
        if r.error:
            line += f" — {r.error}"
        print(line)

    print("\n--- Aggregate metrics ---")
    print(f"  Parse rate:        {parsed}/{len(results)} ({100 * parsed / len(results):.0f}%)")
    print(f"  Violation count:   {violations} (post-enforcement patient text)")
    print(f"  Mean follow-ups:   {mean_followups:.1f} (triage cases, mock path only)")
    print()

    failed = sum(1 for r in results if not r.ok)
    return 1 if failed else 0


async def _main_async(args: argparse.Namespace) -> int:
    use_mock = args.mock

    if not use_mock:
        healthy = await _api_health(args.base_url)
        if not healthy:
            print(
                f"Server not reachable at {args.base_url}/health — falling back to mock mode.",
                file=sys.stderr,
            )
            use_mock = True

    if use_mock:
        results = [await _run_mock_case(c) for c in CANNED_CASES]
        return _print_report(results, "mock")

    async with httpx.AsyncClient(timeout=120.0) as client:
        results = [await _run_api_case(client, args.base_url, c) for c in CANNED_CASES]
    return _print_report(results, f"API @ {args.base_url}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run clinical smoke eval (API or mock).")
    parser.add_argument(
        "--base-url",
        default="http://localhost:8000",
        help="API base URL when server is running (default: http://localhost:8000)",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Force mock reasoning path (no server or API key required)",
    )
    args = parser.parse_args()
    raise SystemExit(asyncio.run(_main_async(args)))


if __name__ == "__main__":
    main()
