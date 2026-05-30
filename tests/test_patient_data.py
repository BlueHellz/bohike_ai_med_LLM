"""Unit tests for patient data provider integration."""

import pytest

from app.integrations.patient_data import (
    FixturePatientDataProvider,
    HttpPatientDataProvider,
    MockPatientDataProvider,
    get_patient_data_provider,
)


@pytest.mark.asyncio
async def test_fixture_provider_returns_profile():
    provider = FixturePatientDataProvider()
    profile = await provider.get_patient_profile("mock-patient-001")
    assert profile.age == 52
    assert profile.sex == "M"
    assert "diabetes" in profile.known_conditions_summary.lower()


@pytest.mark.asyncio
async def test_fixture_provider_unknown_id_returns_empty_profile():
    provider = FixturePatientDataProvider()
    profile = await provider.get_patient_profile("unknown-id")
    assert profile.age is None
    assert profile.known_conditions_summary == ""


@pytest.mark.asyncio
async def test_http_provider_raises_not_implemented():
    provider = HttpPatientDataProvider()
    with pytest.raises(NotImplementedError, match="HTTP patient backend"):
        await provider.get_patient_profile("any-id")


def test_factory_defaults_to_fixture_provider():
    provider = get_patient_data_provider()
    assert isinstance(provider, FixturePatientDataProvider)


def test_mock_provider_alias():
    assert MockPatientDataProvider is FixturePatientDataProvider
