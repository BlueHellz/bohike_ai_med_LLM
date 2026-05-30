"""Tests for AEGIS training pipeline scaffolds."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from app.schemas import ReasoningOutput
from training.pipeline import (
    deidentify_text,
    load_registry,
    shard_records,
    structure_record,
    validate_unified_record,
)
from training.synthetic_clinic.generator import (
    build_manifesto_sample,
    generate_samples,
    validate_sample_patient_text,
)

ROOT = Path(__file__).resolve().parents[1]


class TestDeidentify:
    def test_scrubs_name(self):
        text = "Patient John Smith presented with fever."
        result = deidentify_text(text)
        assert "[NAME]" in result
        assert "John Smith" not in result

    def test_scrubs_date_slash(self):
        text = "Admission on 03/15/2024 for observation."
        result = deidentify_text(text)
        assert "[DATE]" in result
        assert "03/15/2024" not in result

    def test_scrubs_iso_date(self):
        text = "Follow-up scheduled 2024-06-01."
        result = deidentify_text(text)
        assert "[DATE]" in result

    def test_scrubs_mrn(self):
        text = "MRN: ABC123456 noted in chart."
        result = deidentify_text(text)
        assert "[ID]" in result


class TestShard:
    def test_split_fractions(self):
        records = list(range(100))
        shards = shard_records(records, train=0.8, validation=0.1, test=0.1, seed=42)
        assert len(shards["train"]) == 80
        assert len(shards["validation"]) == 10
        assert len(shards["test"]) == 10

    def test_deterministic_with_seed(self):
        records = [{"id": i} for i in range(20)]
        a = shard_records(records, seed=99)
        b = shard_records(records, seed=99)
        assert a == b

    def test_invalid_split_raises(self):
        with pytest.raises(ValueError):
            shard_records([1, 2, 3], train=0.5, validation=0.3, test=0.3)


class TestStructure:
    def test_valid_unified_record(self):
        normalized = {
            "source": "meddialog",
            "patient_text": "I have a headache.",
            "clinician_text": "",
            "note_text": "",
        }
        record = structure_record(normalized, record_type="dialogue")
        errors = validate_unified_record(record)
        assert errors == []
        assert record["type"] == "dialogue"
        assert "headache" in record["text"]

    def test_invalid_type_rejected(self):
        with pytest.raises(ValueError):
            structure_record({"source": "x", "note_text": "text"}, record_type="invalid")

    def test_missing_field_detected(self):
        errors = validate_unified_record({"source": "x", "text": "hi", "type": "qa"})
        assert any("metadata" in e for e in errors)


class TestRegistry:
    def test_registry_has_ten_datasets(self):
        datasets = load_registry()
        assert len(datasets) == 10

    def test_registry_fields(self):
        datasets = load_registry()
        for ds in datasets:
            assert "name" in ds
            assert ds["access_type"] in ("physionet_citi", "i2b2_dua", "open")
            assert ds["aegis_phase"] in (1, 2, 3, 4)


class TestSyntheticDryRun:
    def test_build_manifesto_sample_keys(self):
        sample = build_manifesto_sample("chest tightness")
        assert "patient_text" in sample
        assert "clinician_questions" in sample
        assert "reasoning_chain" in sample
        assert "triage_level" in sample
        assert "clinician_summary" in sample

    def test_generate_samples_dry_run_aegis_sft(self):
        rows = generate_samples(3, dry_run=True, format="aegis_sft")
        assert len(rows) == 3
        for row in rows:
            assert "ideal" in row
            ReasoningOutput(**row["ideal"])

    def test_safety_violation_detected(self):
        viol = validate_sample_patient_text("You have diabetes and should take 500mg daily.")
        assert len(viol) >= 1

    def test_cli_dry_run(self):
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "training.synthetic_clinic.generator",
                "--count",
                "1",
                "--dry-run",
                "--output",
                str(ROOT / "training/data/synthetic/test_cli.jsonl"),
            ],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "Dry Run" in result.stdout
        out = ROOT / "training/data/synthetic/test_cli.jsonl"
        assert out.exists()
        lines = out.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 1
        data = json.loads(lines[0])
        assert "ideal" in data
