import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base


class Encounter(Base):
    __tablename__ = "encounters"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("patients.id"), nullable=False
    )
    provider_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("providers.id"), nullable=True
    )
    encounter_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    care_setting: Mapped[str] = mapped_column(String(20), default="outpatient")
    department: Mapped[str | None] = mapped_column(String(64), nullable=True)
    transcript_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    chief_complaint: Mapped[str | None] = mapped_column(Text, nullable=True)
    encounter_context: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="draft")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    patient: Mapped["Patient"] = relationship("Patient", back_populates="encounters")
    provider: Mapped["Provider | None"] = relationship("Provider", back_populates="encounters")
    emr_notes: Mapped[list["EmrNote"]] = relationship("EmrNote", back_populates="encounter")
    lab_reports: Mapped[list["LabReport"]] = relationship("LabReport", back_populates="encounter")
    diagnosis_records: Mapped[list["DiagnosisRecord"]] = relationship(
        "DiagnosisRecord", back_populates="encounter"
    )
    medication_records: Mapped[list["MedicationRecord"]] = relationship(
        "MedicationRecord", back_populates="encounter"
    )


class EmrNote(Base):
    __tablename__ = "emr_notes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    encounter_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("encounters.id"), nullable=False
    )
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    soap_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    note_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    conversation_duration_seconds: Mapped[int | None] = mapped_column(nullable=True)
    source: Mapped[str] = mapped_column(String(32), default="unknown")
    context_trace_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    is_final: Mapped[bool] = mapped_column(Boolean, default=False)
    version: Mapped[int] = mapped_column(default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    encounter: Mapped["Encounter"] = relationship("Encounter", back_populates="emr_notes")


class EmrTask(Base):
    __tablename__ = "emr_tasks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    encounter_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("encounters.id"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False)
    result_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class DiagnosisRecord(Base):
    __tablename__ = "diagnosis_records"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("patients.id"), nullable=False
    )
    encounter_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("encounters.id"), nullable=True
    )
    icd_code: Mapped[str | None] = mapped_column(String(16), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    diagnosed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    encounter: Mapped["Encounter | None"] = relationship("Encounter", back_populates="diagnosis_records")


class MedicationRecord(Base):
    __tablename__ = "medication_records"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("patients.id"), nullable=False
    )
    encounter_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("encounters.id"), nullable=True
    )
    drug_name: Mapped[str] = mapped_column(String(256), nullable=False)
    dosage: Mapped[str | None] = mapped_column(String(64), nullable=True)
    frequency: Mapped[str | None] = mapped_column(String(64), nullable=True)
    route: Mapped[str | None] = mapped_column(String(32), nullable=True)
    start_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    end_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    encounter: Mapped["Encounter | None"] = relationship("Encounter", back_populates="medication_records")


class LabReport(Base):
    __tablename__ = "lab_reports"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("patients.id"), nullable=False
    )
    encounter_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("encounters.id"), nullable=True
    )
    report_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    report_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    summary_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    encounter: Mapped["Encounter | None"] = relationship("Encounter", back_populates="lab_reports")
    results: Mapped[list["LabResult"]] = relationship("LabResult", back_populates="report")


class LabResult(Base):
    __tablename__ = "lab_results"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    report_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("lab_reports.id"), nullable=False
    )
    test_name: Mapped[str] = mapped_column(String(128), nullable=False)
    value: Mapped[str | None] = mapped_column(String(64), nullable=True)
    unit: Mapped[str | None] = mapped_column(String(32), nullable=True)
    reference_range: Mapped[str | None] = mapped_column(String(64), nullable=True)
    abnormal_flag: Mapped[str | None] = mapped_column(String(16), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    report: Mapped["LabReport"] = relationship("LabReport", back_populates="results")


class AllergyRecord(Base):
    __tablename__ = "allergy_records"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("patients.id"), nullable=False
    )
    allergen: Mapped[str] = mapped_column(String(256), nullable=False)
    reaction: Mapped[str | None] = mapped_column(String(256), nullable=True)
    severity: Mapped[str | None] = mapped_column(String(32), nullable=True)
    onset_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
