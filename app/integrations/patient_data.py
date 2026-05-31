"""
Stub profile providers for consultation context assembly.

Fixtures supply static demographic and clinical-summary fields only (age, sex,
conditions, medications, allergies) when the external patient backend is not
yet connected. Consultation text and voice (POST /messages) are always live
clinical input — they are never substituted from fixtures or labeled as mock.
"""

from __future__ import annotations

import json
import os
from abc import ABC, abstractmethod
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import PatientProfileDB
from app.schemas import PatientProfile

FIXTURES_PATH = Path(__file__).resolve().parents[2] / "fixtures" / "patients.json"


class PatientDataProvider(ABC):
    """Contract for retrieving patient demographic and clinical summary data."""

    @abstractmethod
    async def get_patient_profile(self, patient_id: str) -> PatientProfile:
        """Return a patient profile for the given identifier."""


class FixturePatientDataProvider(PatientDataProvider):
    """Stub profile provider backed by fixtures/patients.json for local dev and tests."""

    # Demographics and clinical summaries only; consultation messages are excluded.

    def __init__(self) -> None:
        self._fixtures: dict[str, PatientProfile] = {}
        if FIXTURES_PATH.exists():
            payload = json.loads(FIXTURES_PATH.read_text())
            for entry in payload.get("patients", []):
                patient_id = entry.pop("patient_id")
                self._fixtures[patient_id] = PatientProfile(**entry)

    async def get_patient_profile(self, patient_id: str) -> PatientProfile:
        return self._fixtures.get(patient_id, PatientProfile())


class HttpPatientDataProvider(PatientDataProvider):
    """Placeholder for a future HTTP-backed patient record service."""

    async def get_patient_profile(self, patient_id: str) -> PatientProfile:
        backend_url = os.getenv("PATIENT_BACKEND_URL", "")
        raise NotImplementedError(
            "HTTP patient backend is not implemented. "
            f"Configure PATIENT_BACKEND_URL (currently: {backend_url!r}) "
            "when the external patient service is available, "
            "or set PATIENT_DATA_PROVIDER=fixture for stub profile data."
        )


# Backward-compatible alias; prefer FixturePatientDataProvider in new code.
MockPatientDataProvider = FixturePatientDataProvider


def get_patient_data_provider() -> PatientDataProvider:
    """Return the configured stub profile provider (fixture or HTTP)."""
    mode = os.getenv("PATIENT_DATA_PROVIDER", "fixture").lower()
    if mode == "http":
        return HttpPatientDataProvider()
    # Legacy PATIENT_DATA_PROVIDER value "mock"; behaviour matches fixture profiles.
    return FixturePatientDataProvider()


async def resolve_patient_profile(db: AsyncSession, patient_id: str) -> PatientProfile:
    """
    Resolve patient profile for consultation context.

    Local DB rows (written via PUT /patients/{id}/profile) take precedence.
    When no DB row exists, the configured provider supplies fixture or remote data.

    Session messages (POST /messages) are separate: they are persisted and passed
    through load_context as current_input and are always treated as live input.
    """
    row = await db.get(PatientProfileDB, patient_id)
    if row:
        return PatientProfile(
            age=row.age,
            sex=row.sex,
            known_conditions_summary=row.known_conditions_summary or "",
            medications_summary=row.medications_summary or "",
            allergies_summary=row.allergies_summary or "",
        )
    provider = get_patient_data_provider()
    return await provider.get_patient_profile(patient_id)
