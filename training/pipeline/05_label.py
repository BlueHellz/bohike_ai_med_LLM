#!/usr/bin/env python3
"""Stage 05 — Optional DeepSeek auto-labeling (dry-run by default)."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from training.pipeline import ROOT, load_config, read_jsonl, write_jsonl

LABEL_PROMPT = """Analyze the following clinical text and return JSON with:
- symptoms (list of strings)
- red_flags (list of strings)
- followup_questions (list of strings)
- reasoning_chain (list of strings)
- triage_level (routine | urgent | emergency)

Clinical text:
{text}
"""


def label_record(text: str, *, dry_run: bool) -> dict:
    if dry_run:
        return {
            "symptoms": [],
            "red_flags": [],
            "followup_questions": [],
            "reasoning_chain": [],
            "triage_level": "routine",
            "_dry_run": True,
        }

    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        print("DEEPSEEK_API_KEY not set. Use --dry-run or configure the key in the environment.", file=sys.stderr)
        sys.exit(1)

    from openai import OpenAI

    client = OpenAI(api_key=api_key, base_url=os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com"))
    model = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "Return valid JSON only."},
            {"role": "user", "content": LABEL_PROMPT.format(text=text[:4000])},
        ],
        temperature=0.2,
    )
    content = response.choices[0].message.content or "{}"
    return json.loads(content)


def main() -> None:
    parser = argparse.ArgumentParser(description="Auto-label structured records via DeepSeek")
    parser.add_argument("--input", type=Path, help="Input unified JSONL")
    parser.add_argument("--output", type=Path, help="Output labeled JSONL")
    parser.add_argument("--dry-run", action="store_true", help="Skip API calls (default when --live omitted)")
    parser.add_argument("--live", action="store_true", help="Call DeepSeek API (requires DEEPSEEK_API_KEY)")
    args = parser.parse_args()

    dry_run = not args.live

    cfg = load_config()
    in_dir = ROOT / cfg["paths"]["structured_dir"]
    out_dir = ROOT / cfg["paths"]["labeled_dir"]
    out_dir.mkdir(parents=True, exist_ok=True)

    inputs = [args.input] if args.input else list(in_dir.rglob("*.jsonl"))
    if not inputs:
        print(f"No input files under {in_dir}. Stage 05 stub: nothing to process.")
        return

    for inp in inputs:
        records = read_jsonl(inp)
        labeled = []
        for rec in records:
            labels = label_record(rec.get("text", ""), dry_run=dry_run)
            labeled.append({**rec, "labels": labels})
        out_path = args.output or out_dir / inp.relative_to(in_dir)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        write_jsonl(out_path, labeled)
        mode = "dry-run" if dry_run else "live"
        print(f"Labeled {len(labeled)} record(s) [{mode}] → {out_path}")


if __name__ == "__main__":
    main()
