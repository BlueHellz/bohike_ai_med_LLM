# AEGIS Training Pipeline

Scaffolded data ingestion, labeling, sharding, and DeepSeek SFT export for the AEGIS Medical AI Consultation Engine.

Full curriculum and dataset catalogue: [docs/AEGIS_TRAINING_BLUEPRINT.md](../docs/AEGIS_TRAINING_BLUEPRINT.md)

## Directory layout

```
training/
├── README.md
├── requirements.txt
├── datasets/
│   └── registry.yaml          # 10 approved datasets with access types
├── pipeline/
│   ├── config.yaml
│   ├── 01_acquire.py          # Manual download instructions (no MIMIC auto-fetch)
│   ├── 02_normalize.py
│   ├── 03_deidentify.py
│   ├── 04_structure.py
│   ├── 05_label.py            # DeepSeek auto-label (--dry-run default)
│   ├── 06_shard.py
│   └── 07_export_deepseek.py
├── schemas/
│   ├── unified_record.json
│   └── aegis_sft_record.json
├── synthetic_clinic/
│   └── generator.py           # Phase 1 synthetic conversations
└── data/                      # Gitignored artefact directories
    ├── raw/
    ├── normalized/
    ├── deidentified/
    ├── structured/
    ├── labeled/
    ├── shards/
    ├── export/
    └── synthetic/v1/
```

## Prerequisites

```bash
pip install -r requirements.txt
pip install -r training/requirements.txt   # pyyaml, tqdm (optional pipeline deps)
```

Set `DEEPSEEK_API_KEY` in the environment for live labeling and synthetic generation. Never commit API keys.

## Pipeline stages

Run from repository root:

```bash
# Stage 01 — print acquisition instructions (no automatic PhysioNet download)
python training/pipeline/01_acquire.py

# Stage 02 — normalize raw JSONL to standard fields
python training/pipeline/02_normalize.py

# Stage 03 — PHI regex scrubber ([NAME], [DATE], [LOCATION], [ID])
python training/pipeline/03_deidentify.py

# Stage 04 — unified JSONL schema
python training/pipeline/04_structure.py --type clinical_note

# Stage 05 — optional DeepSeek labels (dry-run unless --live)
python training/pipeline/05_label.py --dry-run

# Stage 06 — train / val / test split (80/10/10)
python training/pipeline/06_shard.py

# Stage 07 — DeepSeek fine-tune JSONL export
python training/pipeline/07_export_deepseek.py
```

## Synthetic clinic generator (Phase 1)

Generate safe synthetic training samples without real patient data:

```bash
# Dry-run: print prompt template + write stub samples (no API)
python -m training.synthetic_clinic.generator --count 10 --dry-run \
  --output training/data/synthetic/v1/samples.jsonl

# Live generation (requires DEEPSEEK_API_KEY)
python -m training.synthetic_clinic.generator --count 10 \
  --output training/data/synthetic/v1/samples.jsonl

# Manifesto format (blueprint schema)
python -m training.synthetic_clinic.generator --count 5 --format manifesto --dry-run
```

Output formats:

- `manifesto` — blueprint sample (`patient_text`, `clinician_questions`, `reasoning_chain`, `triage_level`, `clinician_summary`)
- `aegis_sft` — `messages` + `ideal` ReasoningOutput row for fine-tuning

Safety validation reuses `app.agents.safety._violations` patterns on patient-facing text.

## Dataset registry

See `datasets/registry.yaml` for all 10 datasets, access types (`physionet_citi`, `i2b2_dua`, `open`), URLs, and AEGIS training phases.

## Related documentation

- [AEGIS Training Blueprint](../docs/AEGIS_TRAINING_BLUEPRINT.md)
- [Fine-Tuning Preparation](../docs/FINE_TUNING_PREP.md)
- [Training and Quality](../docs/TRAINING_AND_QUALITY.md)
