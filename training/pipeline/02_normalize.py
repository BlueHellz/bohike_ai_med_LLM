#!/usr/bin/env python3
"""Stage 02 — Normalization: UTF-8 encoding and field mapping."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from training.pipeline import ROOT, load_config, normalize_record, read_jsonl, write_jsonl


def main() -> None:
    parser = argparse.ArgumentParser(description="Normalize raw records to standard fields")
    parser.add_argument("--input", type=Path, help="Input JSONL (default: raw_dir/*.jsonl)")
    parser.add_argument("--output", type=Path, help="Output JSONL path")
    args = parser.parse_args()

    cfg = load_config()
    raw_dir = ROOT / cfg["paths"]["raw_dir"]
    out_dir = ROOT / cfg["paths"]["normalized_dir"]
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.input:
        inputs = [args.input]
    else:
        inputs = list(raw_dir.rglob("*.jsonl"))

    if not inputs:
        print(f"No input files found under {raw_dir}. Stage 02 stub: nothing to process.")
        return

    for inp in inputs:
        records = read_jsonl(inp)
        normalized = [normalize_record(r) for r in records]
        out_path = args.output or out_dir / inp.relative_to(raw_dir)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        write_jsonl(out_path, normalized)
        print(f"Normalized {len(normalized)} record(s) → {out_path}")


if __name__ == "__main__":
    main()
