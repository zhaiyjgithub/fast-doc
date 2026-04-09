import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base


class Patient(Base):
    __tablename__ = "patients"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    mrn: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    first_name: Mapped[str] = mapped_column(String(64), nullable=False)
    last_name: Mapped[str] = mapped_column(String(64), nullable=False)
    date_of_birth: Mapped[date | None] = mapped_column(Date, nullable=True)
    gender: Mapped[str | None] = mapped_column(String(16), nullable=True)
    primary_language: Mapped[str] = mapped_column(String(16), default="en-US")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    demographics: Mapped["PatientDemographics | None"] = relationship(
        "PatientDemographics", back_populates="patient", uselist=False
    )
    encounters: Mapped[list["Encounter"]] = relationship("Encounter", back_populates="patient")


class PatientDemographics(Base):
    __tablename__ = "patient_demographics"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    patient_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    ssn_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    ssn_last4: Mapped[str | None] = mapped_column(String(4), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    email: Mapped[str | None] = mapped_column(String(128), nullable=True)
    address_line1: Mapped[str | None] = mapped_column(String(256), nullable=True)
    city: Mapped[str | None] = mapped_column(String(64), nullable=True)
    state: Mapped[str | None] = mapped_column(String(4), nullable=True)
    zip_code: Mapped[str | None] = mapped_column(String(16), nullable=True)
    insurance_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    allergy_summary_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    patient: Mapped["Patient"] = relationship("Patient", back_populates="demographics")
