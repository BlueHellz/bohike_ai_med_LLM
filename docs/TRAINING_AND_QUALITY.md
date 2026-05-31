# Consultation Quality and Training

## Overview

The AEGIS consultation engine achieves clinical dialogue quality through structured
prompt engineering, bounded context assembly, a deterministic safety layer, and rolling
session summarisation. Fine-tuning is **not** required for initial deployment.

Quality is enforced at four layers:

| Layer | Mechanism |
|-------|-----------|
| Prompts | Mode-specific system prompts (`triage`, `education`, `review`) with fixed JSON schema |
| Context | `ClinicalContext` — patient profile, rolling summary, recent turns only |
| Safety | Regex enforcement, escalation rules, repair pass, structured fallback |
| Memory | DeepSeek rolling summariser caps long-session drift |

## Profile stub vs live consultation input

| Source | What it supplies | Stubbed? |
|--------|------------------|----------|
| Fixture profile / DB profile | Demographics and clinical summaries for context assembly | Yes — until external patient backend is connected |
| `POST /sessions/{id}/messages` | Patient text or transcribed voice for the current turn | **No** — always live clinical input |

The consultation code path never labels or skips message content as mock:

`TurnRequest` → `load_context` → `current_input` → `run_reasoning`

Only `ClinicalContext.patient_profile` may come from `fixtures/patients.json` or
`PUT /patients/{id}/profile`. Message text is persisted as `SessionMessage` rows and
passed to the LLM unchanged.

## Why fine-tuning is deferred

Fine-tuning is a Phase 2 capability, not a day-one requirement.

**Dataset size and quality for medical SFT.** Supervised fine-tuning for clinical
dialogue demands a large, de-identified corpus of consultation turns with validated
clinician-layer labels. Curating that dataset to enterprise medical standards
(governance review, label consistency, specialty coverage) exceeds what a greenfield
MVP can assume at launch.

**Safety and regulatory validation.** A fine-tuned model requires re-validation of
safety behaviour (escalation, emergency detection, content stripping) under change
control. Prompt-and-schema enforcement provides auditable, deterministic guardrails
that are easier to regression-test before any custom weights are promoted.

**Prompt + structured pipeline delivers MVP quality.** Mode-specific prompts,
`ReasoningOutput` JSON schema, the safety module, and rolling summarisation already
constrain model behaviour for triage, education, and review. This stack is sufficient
for initial deployment and physician oversight workflows.

**Fine-tune follows eval harness and live DeepSeek baseline.** Promotion of a
custom model should occur only after the eval harness (Phase 9 clinical QA) passes
against the production DeepSeek baseline under representative scenarios. That baseline
establishes measurable gates before fine-tuned weights are considered.

**Steps to start fine-tuning when ready (high level):**

See **[FINE_TUNING_PREP.md](FINE_TUNING_PREP.md)** for the full preparation guide (data volume,
compliance, JSONL format, quality gates, baseline metrics, DeepSeek platform steps, and phase
timeline).

Summary:

1. Export de-identified consultation turns with clinician-layer labels after governance sign-off.
2. Format as JSONL instruction pairs aligned with `ReasoningOutput`.
3. Submit to the DeepSeek fine-tuning platform (or compatible endpoint).
4. Point `DEEPSEEK_MODEL` at the fine-tuned deployment name in a staging environment.
5. Re-run the full eval harness; compare safety and quality metrics to the live DeepSeek baseline.
6. Promote only after eval gates pass and clinical governance approves.

## Day-one quality (no fine-tuning)

Structured outputs (`ReasoningOutput`) constrain the model to separate patient-facing
text from the clinician layer. The safety module strips diagnosis and dosing language
from patient responses and prepends emergency disclaimers when high-severity risk flags
are present.

Physician review is triggered automatically when `requires_physician_review` or
`emergency_detected` is set in the safety decision.

## Source citations (patient responses)

When the model makes factual medical statements (mechanisms, epidemiology, care pathways,
symptom associations), it adds brief medically-based source references. Default mode
(`citation_depth=simple`) uses short inline parentheticals such as
`(Source: NHS — headache red flags)` plus a `source_citations` array for UI chips — at
most two cites per reply unless emergency triage. Detailed mode (`citation_depth=detailed`)
adds a short `References:` block at the end of the patient text. Citations are never used
for patient-specific diagnoses. The safety layer still appends standard and emergency
disclaimers independently; citations do not replace those disclaimers.

## Optional future paths

### Fine-tuning DeepSeek

1. Export de-identified consultation turns with clinician-layer labels from production
   (after governance review).
2. Format as JSONL instruction pairs aligned with `ReasoningOutput` schema.
3. Submit to the DeepSeek fine-tuning platform (or compatible OpenAI-style endpoint).
4. Point `DEEPSEEK_MODEL` at the fine-tuned deployment name.
5. Re-run the eval harness (below) before promotion.

### RAG over clinical guidelines

1. Ingest guideline corpora (NICE, local protocols) into a vector index.
2. Inject retrieved passages into `ClinicalContext` or a dedicated retrieval field.
3. Gate retrieval by consultation mode (e.g. education vs triage).

### Eval harness (Phase 9 clinical QA)

Reference scenarios should cover:

- Emergency keyword detection and disclaimer injection
- Malformed JSON recovery (DeepSeek retry + safety fallback)
- Content violation stripping (diagnosis, dosing)
- Physician alert creation on high-severity flags

## Eval smoke tests (DeepSeek-only)

With `LLM_PROVIDER=deepseek` and `MOCK_LLM` unset, live smoke tests require a valid
`DEEPSEEK_API_KEY` in the local `.env` file (never committed).

Automated regression (no API key required):

```bash
python -m pytest tests/ -v
```

Integration tests inject mock LLM callers and validate safety, routing, and API
contracts without external network calls.

For manual live smoke after key configuration, see [GETTING_STARTED.md](GETTING_STARTED.md).

Automated smoke (five canned scenarios):

```bash
python scripts/eval_clinical_smoke.py
python scripts/eval_clinical_smoke.py --mock
```

Expected: HTTP 200 (API mode), `patient_response_text` present, no clinician layer in the
patient-facing response body.

## Training pipeline status

A runnable training scaffold is available under `training/`:

- Dataset registry (`training/datasets/registry.yaml`) — 10 approved de-identified sources
- Ingestion pipeline stages 01–07 (acquire through DeepSeek export)
- Phase 1 synthetic clinic generator (`training/synthetic_clinic/generator.py`)

Full curriculum and access requirements: **[AEGIS_TRAINING_BLUEPRINT.md](AEGIS_TRAINING_BLUEPRINT.md)**

Pipeline commands and directory layout: **[training/README.md](../training/README.md)**

Automated dataset download (especially PhysioNet/MIMIC) is intentionally **not** implemented — acquisition requires manual credentialing (CITI, DUAs). See stage `01_acquire.py` for per-dataset instructions.
