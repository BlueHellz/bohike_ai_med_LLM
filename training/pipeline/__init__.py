"""Shared utilities for the AEGIS training pipeline."""

from __future__ import annotations

import json
import random
import re
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = Path(__file__).resolve().parent / "config.yaml"

PHI_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\b[A-Z][a-z]+ [A-Z][a-z]+\b"), "[NAME]"),
    (re.compile(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b"), "[DATE]"),
    (re.compile(r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]* \d{1,2},? \d{4}\b", re.I), "[DATE]"),
    (re.compile(r"\b\d{4}-\d{2}-\d{2}\b"), "[DATE]"),
    (re.compile(r"\b(?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd)\b[^,\n]{0,40}", re.I), "[LOCATION]"),
    (re.compile(r"\b(?:MRN|Patient ID|Account #?)\s*:?\s*\w+\b", re.I), "[ID]"),
    (re.compile(r"\b\d{6,}\b"), "[ID]"),
]

RECORD_TYPES = frozenset({"clinical_note", "dialogue", "qa", "guideline"})


def load_config(config_path: Path | None = None) -> dict[str, Any]:
    path = config_path or DEFAULT_CONFIG
    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def load_registry(registry_path: Path | None = None) -> list[dict[str, Any]]:
    cfg = load_config()
    path = registry_path or ROOT / cfg["registry"]
    with path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    return data["datasets"]


def deidentify_text(text: str) -> str:
    """Second-pass PHI scrubber: names, dates, locations, IDs."""
    result = text
    for pattern, replacement in PHI_PATTERNS:
        result = pattern.sub(replacement, result)
    return result


def normalize_record(raw: dict[str, Any]) -> dict[str, Any]:
    """Map heterogeneous raw fields to standard text slots."""
    patient = raw.get("patient_text") or raw.get("patient") or ""
    clinician = raw.get("clinician_text") or raw.get("clinician") or ""
    note = raw.get("note_text") or raw.get("text") or raw.get("note") or ""
    return {
        "patient_text": str(patient).encode("utf-8", errors="replace").decode("utf-8"),
        "clinician_text": str(clinician).encode("utf-8", errors="replace").decode("utf-8"),
        "note_text": str(note).encode("utf-8", errors="replace").decode("utf-8"),
        "diagnosis_codes": raw.get("diagnosis_codes") or [],
        "labs_vitals": raw.get("labs_vitals") or raw.get("labs") or {},
        "source": raw.get("source", "unknown"),
    }


def structure_record(
    normalized: dict[str, Any],
    *,
    record_type: str = "clinical_note",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Convert normalized fields to unified JSONL schema."""
    if record_type not in RECORD_TYPES:
        raise ValueError(f"Invalid record type: {record_type}")
    text_parts = [
        normalized.get("patient_text", ""),
        normalized.get("clinician_text", ""),
        normalized.get("note_text", ""),
    ]
    combined = "\n".join(p for p in text_parts if p).strip()
    return {
        "source": normalized.get("source", "unknown"),
        "text": combined,
        "type": record_type,
        "metadata": metadata
        or {
            "specialty": normalized.get("specialty", ""),
            "encounter_type": normalized.get("encounter_type", ""),
            "risk_level": normalized.get("risk_level", ""),
            "tags": normalized.get("tags", []),
        },
    }


def validate_unified_record(record: dict[str, Any]) -> list[str]:
    """Validate record against unified schema requirements."""
    errors: list[str] = []
    for field in ("source", "text", "type", "metadata"):
        if field not in record:
            errors.append(f"missing required field: {field}")
    if record.get("type") and record["type"] not in RECORD_TYPES:
        errors.append(f"invalid type: {record['type']}")
    if not isinstance(record.get("metadata"), dict):
        errors.append("metadata must be an object")
    return errors


def shard_records(
    records: list[Any],
    *,
    train: float = 0.8,
    validation: float = 0.1,
    test: float = 0.1,
    seed: int = 42,
) -> dict[str, list[Any]]:
    """Deterministic train/validation/test split."""
    total = train + validation + test
    if abs(total - 1.0) > 1e-6:
        raise ValueError(f"Split fractions must sum to 1.0, got {total}")
    shuffled = list(records)
    rng = random.Random(seed)
    rng.shuffle(shuffled)
    n = len(shuffled)
    train_end = int(n * train)
    val_end = train_end + int(n * validation)
    return {
        "train": shuffled[:train_end],
        "validation": shuffled[train_end:val_end],
        "test": shuffled[val_end:],
    }


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    if not path.exists():
        return records
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for record in records:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
