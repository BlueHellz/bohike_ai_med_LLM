#!/usr/bin/env python3
"""Stage 01 — Raw data acquisition instructions (no automatic MIMIC download)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from training.pipeline import ROOT, load_config, load_registry

PHYSIONET_DATASETS = {
    "MIMIC-III",
    "MIMIC-IV",
    "MIMIC-IV-Note",
    "eICU Collaborative Research Database",
    "MedNLI",
}


def print_acquire_instructions(dataset: dict) -> None:
    name = dataset["name"]
    access = dataset["access_type"]
    url = dataset["url"]
    notes = dataset.get("notes", "")

    print(f"\n{'=' * 60}")
    print(f"Dataset: {name}")
    print(f"Phase:   {dataset['aegis_phase']}")
    print(f"URL:     {url}")
    print(f"Access:  {access}")
    if notes:
        print(f"Notes:   {notes}")

    if access == "physionet_citi":
        print(
            "\nMANUAL STEPS (PhysioNet — no automatic download):\n"
            "  1. Complete CITI 'Data or Specimens Only Research' training\n"
            "  2. Register at https://physionet.org/settings/credentialing/\n"
            "  3. Sign the dataset-specific Data Use Agreement on PhysioNet\n"
            "  4. Download via the PhysioNet web UI or wget with credentialed access\n"
            "  5. Place extracted files under training/data/raw/<dataset_slug>/"
        )
        if name in PHYSIONET_DATASETS:
            print("  ⚠  This pipeline does NOT auto-download PhysioNet datasets.")
    elif access == "i2b2_dua":
        print(
            "\nMANUAL STEPS (i2b2 / n2c2):\n"
            "  1. Visit the n2c2 portal and sign the Data Use Agreement\n"
            "  2. Download approved challenge corpora\n"
            "  3. Place files under training/data/raw/i2b2/"
        )
    else:
        print(
            "\nMANUAL STEPS (open access):\n"
            "  1. Clone or download from the URL above\n"
            "  2. Place files under training/data/raw/<dataset_slug>/"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Print dataset acquisition instructions")
    parser.add_argument("--dataset", help="Filter by dataset name (substring match)")
    parser.add_argument("--config", type=Path, default=None)
    args = parser.parse_args()

    cfg = load_config(args.config)
    raw_dir = ROOT / cfg["paths"]["raw_dir"]
    raw_dir.mkdir(parents=True, exist_ok=True)

    datasets = load_registry()
    if args.dataset:
        datasets = [d for d in datasets if args.dataset.lower() in d["name"].lower()]

    print("AEGIS Training Pipeline — Stage 01: Raw Data Acquisition")
    print(f"Raw data directory: {raw_dir}")
    print("No datasets are downloaded automatically.")

    for ds in datasets:
        print_acquire_instructions(ds)

    print(f"\n{'=' * 60}")
    print(f"Listed {len(datasets)} dataset(s). Proceed to stage 02 after manual download.")


if __name__ == "__main__":
    main()
