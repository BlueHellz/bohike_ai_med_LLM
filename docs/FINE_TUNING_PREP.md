# Fine-Tuning Preparation

Comprehensive preparation guide for supervised fine-tuning (SFT) of the consultation reasoning model. This document covers readiness criteria, data requirements, compliance, evaluation baselines, and DeepSeek platform integration. **Full training pipeline implementation is out of scope** for this repository phase.

For day-one deployment without custom weights, see [TRAINING_AND_QUALITY.md](TRAINING_AND_QUALITY.md).

---

## When to start fine-tuning

Fine-tuning should **not** begin on day zero.

| Gate | Requirement |
|------|-------------|
| Baseline eval complete | Live DeepSeek (`DEEPSEEK_MODEL=deepseek-chat`) evaluated on representative clinical scenarios |
| Metrics recorded | Parse rate, safety violation rate, follow-up question quality on triage cases |
| Governance sign-off | Clinical and legal review of data sources, labelling protocol, and promotion criteria |
| Safety regression plan | `validate_and_enforce` behaviour re-tested after any custom model promotion |

Fine-tuning is a **Phase 2** capability: prompt engineering, structured `ReasoningOutput` schema, and deterministic safety enforcement deliver MVP quality first.

---

## Data requirements

### Volume

| Tier | Examples | Use case |
|------|----------|----------|
| Minimum viable SFT | 500–1,000 | Pilot on narrow domain (e.g. education-only) |
| Recommended production SFT | 2,000–5,000+ | Multi-mode triage, education, review coverage |
| Specialty expansion | 5,000+ per specialty | Cardiology, paediatrics, etc. |

Quality dominates quantity. Five hundred physician-reviewed examples outperform five thousand noisy auto-labels.

### Schema alignment

Every training label must conform to the production `ReasoningOutput` JSON schema defined in `app/schemas.py`:

```json
{
  "patient_response_text": "...",
  "clinician_layer": {
    "summary": "...",
    "key_findings": ["..."],
    "differential_considerations": ["..."],
    "working_diagnosis_areas": ["..."],
    "risk_flags": [
      {"type": "...", "severity": "low|medium|high", "rationale": "..."}
    ],
    "followup_questions": ["..."],
    "recommended_physician_actions": ["..."],
    "confidence_level": "low|medium|high"
  },
  "safety": {
    "should_escalate": false,
    "escalation_reason": null,
    "requires_physician_review": false,
    "emergency_detected": false
  }
}
```

Training examples that omit fields or use free-form text will not match inference-time validation.

### Dataset format (JSONL)

Each line is one supervised example. Align with chat-style fine-tuning APIs:

```json
{
  "messages": [
    {"role": "system", "content": "<mode-specific system prompt with ReasoningOutput schema>"},
    {"role": "user", "content": "<ClinicalContext JSON as sent to run_reasoning>"}
  ],
  "ideal": {
    "patient_response_text": "...",
    "clinician_layer": { "...": "..." },
    "safety": { "...": "..." }
  }
}
```

The `ideal` object (or assistant message content) must be valid `ReasoningOutput` JSON. Export scripts should serialise `ClinicalContext` exactly as `ctx.model_dump_json()` produces at inference time.

---

## Data sources

| Source | Description | Compliance notes |
|--------|-------------|------------------|
| De-identified consult transcripts | Real patient–clinician dialogue with PHI removed | Requires HIPAA-compliant de-identification (Safe Harbor or Expert Determination); institutional IRB or governance approval |
| Synthetic augmentation | LLM-generated dialogues from seed scenarios | Must be labelled and reviewed; risk of hallucinated clinical facts; supplement only, not sole source |
| Licensed corpora | Third-party medical dialogue or guideline Q&A | Verify licence permits model training; no patient PHI without contract |

**Mandatory controls:**

- No patient identifiers (names, MRNs, dates of birth, addresses) in training files
- Document de-identification method and reviewer for each batch
- Separate raw PHI storage from model-training artefacts
- Audit trail for label edits and physician sign-off

---

## Quality gates

Before any example enters the training set:

1. **Physician review** — At least one licensed clinician validates clinical accuracy of the `clinician_layer` and appropriateness of escalation flags.
2. **Patient layer safety** — `patient_response_text` in training labels must **not** contain definitive diagnosis or dosing language. Diagnosis belongs in `clinician_layer` only.
3. **Safety alignment** — `safety.emergency_detected` and `should_escalate` must match scenario severity; emergency cases must not train the model to downplay urgency.
4. **Schema validation** — Automated check: every row parses as `ReasoningOutput` via Pydantic before upload.
5. **Duplicate and contradiction review** — Remove near-duplicate turns and conflicting labels for the same clinical presentation.

---

## Train / validation / test split

| Split | Share | Purpose |
|-------|-------|---------|
| Train | 80% | SFT weight updates |
| Validation | 10% | Hyperparameter and early stopping |
| Test (holdout) | 10% | Final promotion gate; never used during training |

**Holdout emergency cases:** Reserve a fixed set of high-acuity scenarios (chest pain, stroke symptoms, anaphylaxis, suicidal ideation) in the test split only. Promotion requires passing safety metrics on this holdout without regression versus the live DeepSeek baseline.

---

## Baseline metrics (before fine-tuning)

Establish these metrics on **live DeepSeek** (`DEEPSEEK_MODEL=deepseek-chat`) before curating a fine-tune dataset:

| Metric | Definition | Target direction |
|--------|------------|------------------|
| **Parse rate** | Share of turns where raw LLM output parses as valid `ReasoningOutput` before repair | Higher is better; record pre- and post-repair |
| **Violation rate** | Share of turns where `patient_response_text` triggers diagnosis or dosing regex in `app/agents/safety.py` | Lower is better |
| **Follow-up question count** | Mean length of `clinician_layer.followup_questions` on triage-mode inputs | Sufficient for triage (typically ≥1 on ambiguous presentations) |
| **Escalation accuracy** | Agreement between expected emergency/escalation and `safety` fields on labelled holdout | Must not regress post fine-tune |

Collect baselines using:

```bash
python scripts/eval_clinical_smoke.py --base-url http://localhost:8000
python -m pytest tests/ -v
```

Extend with a full eval harness (Phase 9 clinical QA) before promoting custom weights.

---

## DeepSeek fine-tuning (high level)

Official API documentation: [https://api.deepseek.com](https://api.deepseek.com) (fine-tuning and model management endpoints).

Typical workflow:

1. **Prepare JSONL** — Upload format per DeepSeek fine-tune API specification (chat messages with JSON assistant outputs matching `ReasoningOutput`).
2. **Upload dataset** — POST to the platform file/dataset endpoint; obtain dataset ID.
3. **Create fine-tune job** — Specify base model (e.g. `deepseek-chat`), training file, validation file, and hyperparameters per API docs.
4. **Monitor job** — Poll job status until `succeeded` or `failed`; retain job logs for audit.
5. **Deploy custom model** — Note the fine-tuned model ID returned by the platform.
6. **Configure staging** — Set in `.env`:

   ```bash
   DEEPSEEK_MODEL=<fine-tuned-model-id>
   ```

7. **Re-run eval** — Compare all baseline metrics against live DeepSeek; promote only on non-regression and governance approval.

Staging must never point production traffic at a new model until eval gates pass.

---

## What stays mandatory post fine-tune

Custom weights do **not** replace the safety layer.

`app/agents/safety.validate_and_enforce` remains mandatory on every turn:

- JSON parse and repair pass
- Diagnosis and dosing regex stripping from `patient_response_text`
- Emergency disclaimer injection when `emergency_detected` or high-severity flags apply
- Structured fallback on unrecoverable parse failure

Fine-tuning improves reasoning quality; safety enforcement provides deterministic guardrails under change control.

---

## Phase timeline (recommended)

| Phase | Duration | Activities |
|-------|----------|------------|
| **Week 1** | Live DeepSeek + eval | Deploy with `deepseek-chat`; run smoke and integration tests; record baseline metrics |
| **Weeks 2–4** | Dataset curation | De-identify sources; physician labelling; schema validation; train/val/test split |
| **Week 5+** | Fine-tune pilot | Submit JSONL to DeepSeek; deploy to staging; compare metrics; governance review for promotion |

Adjust timelines by dataset size and governance cycle length.

---

## Eval smoke script

`scripts/eval_clinical_smoke.py` runs five canned clinical inputs:

1. Chest pain (emergency triage)
2. Headache (triage follow-up)
3. Hypertension education
4. Shortness of breath (emergency)
5. Medication education

### Usage

```bash
# Live API (server must be running with valid DEEPSEEK_API_KEY)
uvicorn app.main:app --reload --port 8000
python scripts/eval_clinical_smoke.py

# Explicit base URL
python scripts/eval_clinical_smoke.py --base-url http://localhost:8000

# Mock mode — no server or API key; validates routing, parse, and safety on canned LLM output
python scripts/eval_clinical_smoke.py --mock
```

### Output

The script prints per-scenario status and aggregate metrics:

- Parse success rate
- Safety violation count (diagnosis/dosing patterns in patient text after enforcement)
- Mean follow-up question count on triage scenarios

Use these aggregates as a starting baseline before investing in full dataset curation.

---

## Related documentation

- [GETTING_STARTED.md](GETTING_STARTED.md) — Local setup and first live turn
- [TRAINING_AND_QUALITY.md](TRAINING_AND_QUALITY.md) — Day-one quality without fine-tuning
- [AEGIS_TRAINING_BLUEPRINT.md](AEGIS_TRAINING_BLUEPRINT.md) — Full training curriculum, datasets, and pipeline blueprint
- [training/README.md](../training/README.md) — Runnable pipeline scaffolds and synthetic clinic generator
