#!/usr/bin/env python3
"""Stage 06 — Train / validation / test sharding."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from training.pipeline import ROOT, load_config, read_jsonl, shard_records, write_jsonl


def main() -> None:
    parser = argparse.ArgumentParser(description="Split labeled records into train/val/test")
    parser.add_argument("--input", type=Path, help="Input JSONL")
    parser.add_argument("--output-dir", type=Path, help="Output directory for shards")
    args = parser.parse_args()

    cfg = load_config()
    splits = cfg["splits"]
    in_dir = ROOT / cfg["paths"]["labeled_dir"]
    out_dir = args.output_dir or (ROOT / cfg["paths"]["shards_dir"])
    out_dir.mkdir(parents=True, exist_ok=True)

    inputs = [args.input] if args.input else list(in_dir.rglob("*.jsonl"))
    if not inputs:
        print(f"No input files under {in_dir}. Stage 06 stub: nothing to process.")
        return

    all_records = []
    for inp in inputs:
        all_records.extend(read_jsonl(inp))

    if not all_records:
        print("No records to shard.")
        return

    shards = shard_records(
        all_records,
        train=splits["train"],
        validation=splits["validation"],
        test=splits["test"],
        seed=cfg.get("shard_seed", 42),
    )

    for split_name, records in shards.items():
        out_path = out_dir / f"{split_name}.jsonl"
        write_jsonl(out_path, records)
        print(f"Shard {split_name}: {len(records)} record(s) → {out_path}")


if __name__ == "__main__":
    main()
