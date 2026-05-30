#!/usr/bin/env python3
"""Stage 07 — Export AEGIS SFT records to DeepSeek fine-tune message format.

DeepSeek fine-tune format (OpenAI-compatible chat JSONL):
Each line is a JSON object with a "messages" array:

  {
    "messages": [
      {"role": "system", "content": "<system prompt>"},
      {"role": "user", "content": "<ClinicalContext JSON>"},
      {"role": "assistant", "content": "<ReasoningOutput JSON string>"}
    ]
  }

The assistant content must be valid ReasoningOutput JSON matching app/schemas.py.
See training/schemas/aegis_sft_record.json for the intermediate aegis_sft format.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from app.schemas import ReasoningOutput
from training.pipeline import ROOT, load_config, read_jsonl, write_jsonl


def to_deepseek_row(record: dict) -> dict:
    """Convert aegis_sft record to DeepSeek upload format."""
    messages = list(record.get("messages", []))
    ideal = record.get("ideal", {})
    ReasoningOutput(**ideal)

    if messages and messages[-1].get("role") != "assistant":
        messages.append(
            {"role": "assistant", "content": json.dumps(ideal, ensure_ascii=False)}
        )
    elif not messages:
        messages = [
            {"role": "system", "content": "Return ReasoningOutput JSON only."},
            {"role": "user", "content": json.dumps(record.get("clinical_context", {}))},
            {"role": "assistant", "content": json.dumps(ideal, ensure_ascii=False)},
        ]
    return {"messages": messages}


def main() -> None:
    parser = argparse.ArgumentParser(description="Export aegis_sft JSONL to DeepSeek format")
    parser.add_argument("--input", type=Path, help="Input aegis_sft JSONL")
    parser.add_argument("--output", type=Path, help="Output DeepSeek JSONL")
    args = parser.parse_args()

    cfg = load_config()
    default_in = ROOT / cfg["paths"]["shards_dir"] / "train.jsonl"
    default_out = ROOT / cfg["deepseek"]["export_path"]

    inp = args.input or default_in
    out = args.output or default_out

    if not inp.exists():
        synthetic = ROOT / cfg["paths"]["synthetic_dir"] / "samples.jsonl"
        if synthetic.exists():
            inp = synthetic
        else:
            print(f"No input at {inp}. Export stub: write aegis_sft JSONL first.")
            return

    records = read_jsonl(inp)
    exported = []
    for rec in records:
        if "ideal" in rec or "messages" in rec:
            exported.append(to_deepseek_row(rec))
        elif "patient_response_text" in rec:
            exported.append(
                {
                    "messages": [
                        {"role": "system", "content": "Return ReasoningOutput JSON only."},
                        {"role": "user", "content": rec.get("patient_text", rec.get("text", ""))},
                        {
                            "role": "assistant",
                            "content": json.dumps(
                                {
                                    "patient_response_text": rec["patient_response_text"],
                                    "clinician_layer": rec.get("clinician_layer", {}),
                                    "safety": rec.get("safety", {}),
                                },
                                ensure_ascii=False,
                            ),
                        },
                    ]
                }
            )

    write_jsonl(out, exported)
    print(f"Exported {len(exported)} row(s) → {out}")


if __name__ == "__main__":
    main()
