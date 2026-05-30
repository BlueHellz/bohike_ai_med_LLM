#!/usr/bin/env python3
"""Stage 04 — Structure records into unified JSONL schema."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from training.pipeline import (
    ROOT,
    load_config,
    read_jsonl,
    structure_record,
    validate_unified_record,
    write_jsonl,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert records to unified JSONL schema")
    parser.add_argument("--input", type=Path, help="Input JSONL")
    parser.add_argument("--output", type=Path, help="Output JSONL")
    parser.add_argument("--type", default="clinical_note", choices=["clinical_note", "dialogue", "qa", "guideline"])
    parser.add_argument("--strict", action="store_true", help="Exit non-zero on validation errors")
    args = parser.parse_args()

    cfg = load_config()
    in_dir = ROOT / cfg["paths"]["deidentified_dir"]
    out_dir = ROOT / cfg["paths"]["structured_dir"]
    out_dir.mkdir(parents=True, exist_ok=True)

    inputs = [args.input] if args.input else list(in_dir.rglob("*.jsonl"))
    if not inputs:
        print(f"No input files under {in_dir}. Stage 04 stub: nothing to process.")
        return

    total_errors = 0
    for inp in inputs:
        records = read_jsonl(inp)
        structured = []
        for raw in records:
            rec = structure_record(raw, record_type=args.type)
            errors = validate_unified_record(rec)
            if errors:
                total_errors += len(errors)
                print(f"Validation errors in {inp}: {errors}", file=sys.stderr)
            structured.append(rec)
        out_path = args.output or out_dir / inp.relative_to(in_dir)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        write_jsonl(out_path, structured)
        print(f"Structured {len(structured)} record(s) → {out_path}")

    if args.strict and total_errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
