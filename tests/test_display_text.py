"""Tests for patient display text splitting."""

from app.agents.safety import EMERGENCY_DISCLAIMER, STANDARD_DISCLAIMER
from local_tts.display_text import split_patient_display_text


def test_split_standard_disclaimer_at_end():
    body = "Your symptoms may be related to muscle strain."
    text = body + "\n\n" + STANDARD_DISCLAIMER
    clinical, emergency, standard = split_patient_display_text(text)
    assert clinical == body
    assert emergency is None
    assert standard == STANDARD_DISCLAIMER


def test_split_emergency_disclaimer_at_start():
    body = "Chest pain with sweating needs urgent evaluation."
    text = EMERGENCY_DISCLAIMER + "\n\n" + body
    clinical, emergency, standard = split_patient_display_text(text)
    assert clinical == body
    assert emergency == EMERGENCY_DISCLAIMER
    assert standard is None


def test_split_emergency_and_standard():
    body = "Please seek care today."
    text = EMERGENCY_DISCLAIMER + "\n\n" + body + "\n\n" + STANDARD_DISCLAIMER
    clinical, emergency, standard = split_patient_display_text(text)
    assert clinical == body
    assert emergency == EMERGENCY_DISCLAIMER
    assert standard == STANDARD_DISCLAIMER


def test_split_no_disclaimer():
    body = "Rest and fluids may help."
    clinical, emergency, standard = split_patient_display_text(body)
    assert clinical == body
    assert emergency is None
    assert standard is None
