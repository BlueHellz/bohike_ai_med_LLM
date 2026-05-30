# AEGIS Model Training Blueprint

Enterprise training curriculum, data ingestion pipeline, DeepSeek fine-tuning plan, and Phase 1 synthetic clinic generator for the AEGIS Medical AI Consultation Engine.

This document consolidates approved de-identified dataset sources, phased training objectives, pipeline stages, and access requirements. Implementation scaffolds live under `training/` in this repository.

---

## Free, Legal, De-Identified Medical Datasets for AEGIS

### 1. MIMIC-III (MIT)

- **Source:** MIT Laboratory for Computational Physiology
- **Content:** De-identified ICU notes, labs, vitals, diagnoses, procedures
- **Access:** Requires CITI training + data use agreement
- **URL:** https://physionet.org/content/mimiciii/

### 2. MIMIC-IV (MIT)

- Newer, larger version of MIMIC-III
- **Includes:** Clinical notes, radiology reports, labs, vitals, medications
- **Access:** Same as MIMIC-III
- **URL:** https://physionet.org/content/mimiciv/

### 3. MIMIC-IV-Note (MIT)

- Pure clinical notes dataset
- Ideal for training reasoning, summarization, triage logic
- **URL:** https://physionet.org/content/mimic-iv-note/

### 4. eICU Collaborative Research Database (MIT)

- Multi-center ICU dataset
- Supports learning patterns across hospitals
- **URL:** https://physionet.org/content/eicu-crd/

### 5. i2b2/UTHealth Clinical NLP Datasets (Harvard + Partners Healthcare)

- De-identified clinical notes for NLP tasks
- **Includes:** Discharge summaries, smoking status, obesity, medication extraction
- **URL:** https://portal.dbmi.hms.harvard.edu/projects/n2c2-nlp/

### 6. Stanford COVID-19 Clinical Notes Dataset (Stanford)

- De-identified clinical notes related to COVID encounters
- Supports symptom → reasoning pattern training
- **URL:** https://stanfordmlgroup.github.io/competitions/clinical-notes/

### 7. PubMed Open Access Subset (NIH)

- Millions of biomedical articles
- Use for guideline extraction, symptom descriptions, risk factors
- **URL:** https://www.ncbi.nlm.nih.gov/pmc/tools/openftlist/

### 8. MedDialog (Microsoft Research)

- Large dataset of doctor–patient dialogues
- De-identified, multi-language
- Suitable for conversational medical reasoning
- **URL:** https://github.com/UCSD-AI4H/Medical-Dialogue-System

### 9. MedQA / MedMCQA / PubMedQA

- Medical question–answer datasets
- Supports structured reasoning and clinical logic training
- **URLs:**
  - https://github.com/jind11/MedQA
  - https://medmcqa.github.io/
  - https://pubmedqa.github.io/

### 10. MedNLI (NLI for Clinical Text)

- Natural language inference dataset built from clinical notes
- Supports reasoning consistency training
- **URL:** https://physionet.org/content/mednli/

---

## How to Use Datasets for AEGIS Training

### Phase 1 — Build Clinician-Style Reasoning

- **Datasets:** MIMIC-IV-Note + i2b2 + MedDialog
- **Training objectives:**
  - Extract symptoms
  - Ask follow-up questions
  - Identify red flags
  - Produce clinician summaries

### Phase 2 — Build Triage Intelligence

- **Datasets:** MIMIC-IV + eICU
- **Training objectives:**
  - Severity patterns
  - Time-course reasoning
  - Risk stratification

### Phase 3 — Build Medical Knowledge Grounding

- **Datasets:** PubMed OA + MedQA + MedNLI
- **Training objectives:**
  - Guideline-aligned reasoning
  - Evidence-based explanations

### Phase 4 — AEGIS-Specific Fine-Tuning

- **Datasets:** Synthetic Clinic (Phase 1 generator) + real AEGIS conversations (consented + de-identified)
- **Training objectives:**
  - Conversational flow
  - Patient-friendly explanations
  - Personalized follow-up logic
  - Physician summary generation

---

## Dataset Compliance Summary

- All listed sources are **de-identified**.
- All are **approved for research and ML training**.
- Some require:
  - CITI training (free)
  - A simple data use agreement

---

## Complete Model Training Blueprint (Self-Contained)

This section contains:

1. Full Training Curriculum
2. Data Ingestion Pipeline
3. DeepSeek-Ready Training Plan
4. Phase 1 Synthetic Clinic Generator
5. Notes on Access Requirements (CITI, DUAs)

---

## 0. Access Requirements

### MIT datasets (MIMIC-III, MIMIC-IV, eICU, MedNLI)

- Complete CITI "Data or Specimens Only Research" course (free)
- Submit PhysioNet credentialed access request (free)
- No HIPAA issues — data is already de-identified

### i2b2 datasets

- Sign a Data Use Agreement (free)

### PubMed OA, MedDialog, MedQA, MedMCQA

- No signup required

---

## 1. Full Training Curriculum

### Phase 1 — Foundational Clinical Language & Reasoning

**Goal:** Teach the model how clinicians think, write, and structure reasoning.

**Datasets:**

- MIMIC-IV-Note (MIT)
- i2b2 Clinical NLP datasets
- MedDialog (doctor–patient dialogues)
- PubMed Open Access subset

**Training objectives:**

- Clinical summarization
- Symptom extraction
- Follow-up question generation
- Red-flag detection
- SOAP note structure
- Differential-style reasoning (non-diagnostic)

**Outputs:**

- Base Clinician Reasoning Layer
- Red-flag classifier
- Follow-up question generator

### Phase 2 — Triage & Severity Reasoning

**Goal:** Teach the model to reason about urgency, severity, and risk.

**Datasets:**

- MIMIC-IV (structured)
- eICU Collaborative Research Database
- MedNLI (clinical inference)

**Training objectives:**

- Severity classification
- Time-course reasoning
- Risk stratification
- Escalation logic (ER vs urgent care vs routine)

**Outputs:**

- Triage engine
- Risk scoring module
- Escalation decision layer

### Phase 3 — Medical Knowledge Grounding

**Goal:** Teach the model to align with guidelines and evidence.

**Datasets:**

- PubMed OA
- MedQA
- MedMCQA
- PubMedQA

**Training objectives:**

- Evidence-based reasoning
- Guideline-aligned explanations
- Consistency checking
- Clinical logic chains

**Outputs:**

- Knowledge-grounded reasoning layer
- Explanation generator

### Phase 4 — AEGIS-Specific Fine-Tuning

**Goal:** Specialize the model for AEGIS UX and target population.

**Datasets:**

- Synthetic Clinic (Phase 1 generator)
- Real AEGIS conversations (consented + de-identified)

**Training objectives:**

- Conversational flow
- Patient-friendly explanations
- Personalized follow-up logic
- Physician summary generation

**Outputs:**

- AEGIS Reasoning Engine v1
- AEGIS Clinician Summary Engine
- AEGIS Risk & Alert Engine

---

## 2. Data Ingestion Pipeline

### Stage 1 — Raw Data Acquisition

- Download datasets from:
  - PhysioNet (MIMIC, eICU, MedNLI)
  - i2b2 portal
  - GitHub (MedDialog, MedQA, MedMCQA)
  - PubMed OA FTP

### Stage 2 — Normalization

- Convert all text to UTF-8
- Standardize fields:
  - `patient_text`
  - `clinician_text`
  - `note_text`
  - `diagnosis_codes` (if present)
  - `labs/vitals` (if present)
- Remove formatting artifacts

### Stage 3 — De-Identification (Second Pass)

Even though datasets are de-identified:

- Run automated PHI scrubber:
  - Replace names → `[NAME]`
  - Replace dates → `[DATE]`
  - Replace locations → `[LOCATION]`
  - Replace IDs → `[ID]`

### Stage 4 — Structuring

Convert all data into unified JSONL format:

```json
{
  "source": "mimic_iv_note",
  "text": "...",
  "type": "clinical_note | dialogue | qa | guideline",
  "metadata": {
    "specialty": "...",
    "encounter_type": "...",
    "risk_level": "...",
    "tags": []
  }
}
```

### Stage 5 — Labeling (Optional)

- Use DeepSeek to auto-label:
  - symptoms
  - red flags
  - follow-up questions
  - reasoning chains
  - triage level

### Stage 6 — Sharding

- Split into:
  - train
  - validation
  - test

### Stage 7 — Storage

- Store in:
  - S3-compatible bucket
  - or local filesystem
- Use versioning:
  - `dataset_v1/`
  - `dataset_v2/`

Pipeline implementation: `training/pipeline/` (stages 01–07).

---

## 3. DeepSeek-Ready Training Plan

**Goal:** Enable DeepSeek to train, fine-tune, and orchestrate the entire reasoning engine with minimal tokens and maximum structure.

### Component 1 — Base Reasoning Model

- **Train on:** MIMIC-IV-Note, i2b2, MedDialog
- **Objective:** Structured reasoning, follow-up questions, red-flag detection

### Component 2 — Triage Model

- **Train on:** MIMIC-IV structured data, eICU, MedNLI
- **Objective:** Severity classification, escalation logic

### Component 3 — Knowledge Model

- **Train on:** PubMed OA, MedQA, MedMCQA
- **Objective:** Evidence-based reasoning, guideline alignment

### Component 4 — AEGIS Specialization

- **Train on:** Synthetic Clinic, real AEGIS conversations (consented)
- **Objective:** Patient-friendly explanations, clinician summaries, alert generation

### Component 5 — Model Orchestration

DeepSeek handles:

- Routing (triage vs education vs review)
- Safety filtering
- JSON schema enforcement
- Token-efficient summarization

Export script: `training/pipeline/07_export_deepseek.py`

---

## 4. Phase 1 Synthetic Clinic Generator

**Goal:** Generate thousands of safe, realistic, clinician-style conversations without touching real patient data.

**Components:**

1. Patient Narrative Generator
2. Clinician Question Generator
3. Reasoning Chain Generator
4. Red-Flag Injector
5. Summary + Triage Labeler

**Synthetic sample format:**

```json
{
  "patient_text": "I've had chest tightness for 2 hours...",
  "clinician_questions": [
    "When did this start?",
    "Are you short of breath?",
    "Any sweating or nausea?"
  ],
  "reasoning_chain": [
    "Chest tightness + shortness of breath → possible cardiac risk",
    "Duration > 1 hour → increases concern",
    "Needs immediate escalation"
  ],
  "triage_level": "emergency",
  "clinician_summary": "Acute chest symptoms with red flags; recommend ER evaluation."
}
```

**Generation steps:**

1. Generate patient narrative (DeepSeek)
2. Generate clinician follow-up questions (DeepSeek)
3. Generate reasoning chain (DeepSeek)
4. Generate triage level (DeepSeek)
5. Generate clinician summary (DeepSeek)
6. Validate with safety rules
7. Store as training sample

Implementation: `training/synthetic_clinic/generator.py`

---

## 5. Final Notes

Required sign-ups:

- CITI training (free)
- PhysioNet credentialed access (free)
- i2b2 Data Use Agreement (free)

All other listed datasets are immediately downloadable without credentialing.

---

## Related Documentation

- [training/README.md](../training/README.md) — Pipeline commands and directory layout
- [FINE_TUNING_PREP.md](FINE_TUNING_PREP.md) — SFT readiness, schema alignment, quality gates
- [TRAINING_AND_QUALITY.md](TRAINING_AND_QUALITY.md) — Day-one quality without custom weights
