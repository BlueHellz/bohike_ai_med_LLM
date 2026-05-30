#!/usr/bin/env python3
"""Stage 03 — De-identification second pass (PHI regex scrubber)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from training.pipeline import ROOT, deidentify_text, load_config, read_jsonl, write_jsonl

TEXT_FIELDS = ("patient_text", "clinician_text", "note_text", "text")


def deidentify_record(record: dict) -> dict:
    out = dict(record)
    for field in TEXT_FIELDS:
        if field in out and isinstance(out[field], str):
            out[field] = deidentify_text(out[field])
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Run PHI scrubber on normalized records")
    parser.add_argument("--input", type=Path, help="Input JSONL")
    parser.add_argument("--output", type=Path, help="Output JSONL")
    args = parser.parse_args()

    cfg = load_config()
    in_dir = ROOT / cfg["paths"]["normalized_dir"]
    out_dir = ROOT / cfg["paths"]["deidentified_dir"]
    out_dir.mkdir(parents=True, exist_ok=True)

    inputs = [args.input] if args.input else list(in_dir.rglob("*.jsonl"))
    if not inputs:
        print(f"No input files under {in_dir}. Stage 03 stub: nothing to process.")
        return

    for inp in inputs:
        records = read_jsonl(inp)
        cleaned = [deidentify_record(r) for r in records]
        out_path = args.output or out_dir / inp.relative_to(in_dir)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        write_jsonl(out_path, cleaned)
        print(f"De-identified {len(cleaned)} record(s) → {out_path}")


if __name__ == "__main__":
    main()
