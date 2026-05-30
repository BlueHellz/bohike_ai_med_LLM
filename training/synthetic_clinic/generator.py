"""Phase 1 synthetic clinic generator — DeepSeek-backed conversation samples."""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
from pathlib import Path
from typing import Any

from app.agents.safety import _violations
from app.schemas import ClinicianLayer, ReasoningOutput, SafetyDecision

ROOT = Path(__file__).resolve().parents[2]

SCENARIO_SEEDS = [
    "chest tightness and shortness of breath",
    "persistent headache with visual changes",
    "lower back pain after lifting",
    "fever and sore throat for three days",
    "anxiety and palpitations",
    "abdominal pain and nausea",
    "skin rash with itching",
    "dizziness when standing up",
]

PROMPT_TEMPLATE = """Generate a synthetic clinical training sample as JSON with exactly these keys:
- patient_text (string): first-person patient narrative, 2-4 sentences
- clinician_questions (array of 3 strings): follow-up questions
- reasoning_chain (array of 3 strings): non-diagnostic clinical reasoning steps
- triage_level (string): one of routine, urgent, emergency
- clinician_summary (string): brief clinician-facing summary

Scenario focus: {scenario}
Return JSON only, no markdown fences.
"""

REASONING_OUTPUT_PROMPT = """Convert this synthetic clinic sample into AEGIS ReasoningOutput JSON.
Patient narrative must NOT contain definitive diagnosis or dosing.
Include clinician_layer with summary, key_findings, differential_considerations,
working_diagnosis_areas, risk_flags, followup_questions, recommended_physician_actions,
confidence_level. Include safety with should_escalate, requires_physician_review, emergency_detected.

Sample:
{sample}

Return ReasoningOutput JSON only.
"""


def build_manifesto_sample(scenario: str) -> dict[str, Any]:
    """Deterministic stub sample (no API) for dry-run and tests."""
    emergency = "chest" in scenario or "breath" in scenario
    return {
        "patient_text": f"For the past few hours I have noticed {scenario}. It is worrying me.",
        "clinician_questions": [
            "When did this start?",
            "Are there any associated symptoms?",
            "Any relevant medical history?",
        ],
        "reasoning_chain": [
            f"Presenting concern: {scenario}",
            "Duration and associated symptoms need clarification",
            "Escalation if red flags present",
        ],
        "triage_level": "emergency" if emergency else "routine",
        "clinician_summary": f"Patient reports {scenario}; further assessment recommended.",
    }


def validate_sample_patient_text(text: str) -> list[str]:
    """Reuse production safety violation patterns."""
    return _violations(text)


def call_deepseek(prompt: str) -> str:
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        raise RuntimeError("DEEPSEEK_API_KEY not set")

    from openai import OpenAI

    client = OpenAI(api_key=api_key, base_url=os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com"))
    model = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "Return valid JSON only."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.7,
    )
    return response.choices[0].message.content or "{}"


def parse_json_response(raw: str) -> dict[str, Any]:
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    return json.loads(text)


def generate_manifesto_sample(scenario: str, *, dry_run: bool) -> dict[str, Any]:
    if dry_run:
        return build_manifesto_sample(scenario)
    raw = call_deepseek(PROMPT_TEMPLATE.format(scenario=scenario))
    sample = parse_json_response(raw)
    viol = validate_sample_patient_text(sample.get("patient_text", ""))
    if viol:
        sample["patient_text"] = (
            "Based on what has been described, further evaluation with a clinician is recommended."
        )
        sample["_safety_rewritten"] = True
    return sample


def to_reasoning_output(sample: dict[str, Any], *, dry_run: bool) -> dict[str, Any]:
    if dry_run:
        emergency = sample.get("triage_level") == "emergency"
        return ReasoningOutput(
            patient_response_text=sample["patient_text"],
            clinician_layer=ClinicianLayer(
                summary=sample["clinician_summary"],
                key_findings=[sample["reasoning_chain"][0]] if sample.get("reasoning_chain") else [],
                differential_considerations=["Further evaluation needed"],
                working_diagnosis_areas=["Undifferentiated presentation"],
                risk_flags=(
                    [{"type": "chest_pain", "severity": "high", "rationale": "Red flag symptoms"}]
                    if emergency
                    else []
                ),
                followup_questions=sample.get("clinician_questions", []),
                recommended_physician_actions=["Clinical assessment"],
                confidence_level="medium",
            ),
            safety=SafetyDecision(
                should_escalate=emergency,
                requires_physician_review=emergency,
                emergency_detected=emergency,
                escalation_reason="Synthetic emergency scenario" if emergency else None,
            ),
        ).model_dump()

    raw = call_deepseek(REASONING_OUTPUT_PROMPT.format(sample=json.dumps(sample)))
    parsed = parse_json_response(raw)
    output = ReasoningOutput(**parsed)
    viol = validate_sample_patient_text(output.patient_response_text)
    if viol:
        output.patient_response_text = (
            "Further evaluation with a healthcare provider is recommended for these symptoms."
        )
    return output.model_dump()


def generate_samples(
    count: int,
    *,
    dry_run: bool,
    format: str,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for i in range(count):
        scenario = random.choice(SCENARIO_SEEDS)
        manifesto = generate_manifesto_sample(scenario, dry_run=dry_run)
        if format == "manifesto":
            rows.append(manifesto)
        else:
            ideal = to_reasoning_output(manifesto, dry_run=dry_run)
            rows.append(
                {
                    "messages": [
                        {"role": "system", "content": "Return ReasoningOutput JSON only."},
                        {"role": "user", "content": manifesto["patient_text"]},
                    ],
                    "ideal": ideal,
                    "synthetic_meta": {"scenario": scenario, "triage_level": manifesto.get("triage_level")},
                }
            )
    return rows


def write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for record in records:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate synthetic clinic training samples")
    parser.add_argument("--count", type=int, default=1, help="Number of samples to generate")
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "training/data/synthetic/v1/samples.jsonl",
        help="Output JSONL path",
    )
    parser.add_argument(
        "--format",
        choices=["manifesto", "aegis_sft"],
        default="aegis_sft",
        help="Output format: manifesto (blueprint) or aegis_sft (ReasoningOutput row)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print prompt template; use stub samples")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    args = parser.parse_args()

    random.seed(args.seed)

    if args.dry_run:
        print("=== Synthetic Clinic Generator — Dry Run ===")
        print(PROMPT_TEMPLATE.format(scenario=SCENARIO_SEEDS[0]))
        print("\n--- Stub sample ---")
        print(json.dumps(build_manifesto_sample(SCENARIO_SEEDS[0]), indent=2))

    samples = generate_samples(args.count, dry_run=args.dry_run or not os.environ.get("DEEPSEEK_API_KEY"), format=args.format)
    write_jsonl(args.output, samples)
    print(f"Wrote {len(samples)} sample(s) → {args.output}")


if __name__ == "__main__":
    main()
