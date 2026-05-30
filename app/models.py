"""SQLAlchemy ORM models for sessions, messages, alerts, and profiles."""

from datetime import datetime

from sqlalchemy import JSON, Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class Session(Base):
    __tablename__ = "sessions"
    id = Column(String, primary_key=True)
    patient_id = Column(String, nullable=False)
    user_type = Column(String, default="patient")
    mode = Column(String, default="triage")
    channel = Column(String, default="text")
    rolling_summary = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)
    requires_review = Column(Boolean, default=False)
    emergency_flag = Column(Boolean, default=False)
    closed = Column(Boolean, default=False)


class SessionMessage(Base):
    __tablename__ = "session_messages"
    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String, ForeignKey("sessions.id"))
    sender = Column(String)
    text = Column(Text)
    timestamp = Column(DateTime, default=datetime.utcnow)
    channel = Column(String, default="text")


class AISummary(Base):
    __tablename__ = "ai_summaries"
    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String, ForeignKey("sessions.id"))
    clinician_summary = Column(Text)
    key_findings = Column(JSON)
    differential_considerations = Column(JSON)
    working_diagnosis_areas = Column(JSON)
    risk_flags = Column(JSON)
    followup_questions = Column(JSON)
    recommended_physician_actions = Column(JSON)
    confidence_level = Column(String)
    timestamp = Column(DateTime, default=datetime.utcnow)


class Alert(Base):
    __tablename__ = "alerts"
    id = Column(String, primary_key=True)
    patient_id = Column(String)
    session_id = Column(String, ForeignKey("sessions.id"))
    flag_type = Column(String)
    severity = Column(String)
    rationale = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    acknowledged = Column(Boolean, default=False)


class PatientProfileDB(Base):
    __tablename__ = "patient_profiles"
    patient_id = Column(String, primary_key=True)
    age = Column(Integer, nullable=True)
    sex = Column(String, nullable=True)
    known_conditions_summary = Column(Text, default="")
    medications_summary = Column(Text, default="")
    allergies_summary = Column(Text, default="")
    updated_at = Column(DateTime, default=datetime.utcnow)
