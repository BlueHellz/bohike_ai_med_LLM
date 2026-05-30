import json
import os
import tempfile

_test_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
os.environ.setdefault("DB_URL", f"sqlite+aiosqlite:///{_test_db.name}")
os.environ.setdefault("RECENT_TURNS_K", "5")
os.environ.setdefault("LLM_PROVIDER", "deepseek")

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models import Base


@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"


@pytest_asyncio.fixture
async def db_session():
    os.environ.setdefault("RECENT_TURNS_K", "5")
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


def make_reasoning_json(
    patient_text: str,
    risk_flags=None,
    should_escalate=False,
    requires_review=False,
    emergency_detected=False,
):
    risk_flags = risk_flags or []
    return json.dumps(
        {
            "patient_response_text": patient_text,
            "clinician_layer": {
                "summary": "Clinical summary.",
                "key_findings": ["finding one"],
                "differential_considerations": ["option A"],
                "working_diagnosis_areas": ["area of concern"],
                "risk_flags": risk_flags,
                "followup_questions": ["When did this start?"],
                "recommended_physician_actions": [],
                "confidence_level": "medium",
            },
            "safety": {
                "should_escalate": should_escalate,
                "escalation_reason": None,
                "requires_physician_review": requires_review,
                "emergency_detected": emergency_detected,
            },
        }
    )
