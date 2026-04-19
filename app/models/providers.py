import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base


class Provider(Base):
    __tablename__ = "providers"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    external_provider_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    provider_clinic_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    division_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    clinic_system: Mapped[str | None] = mapped_column(String(32), nullable=True)
    clinic_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    first_name: Mapped[str] = mapped_column(String(64), nullable=False)
    last_name: Mapped[str] = mapped_column(String(64), nullable=False)
    full_name: Mapped[str] = mapped_column(String(128), nullable=False)
    gender: Mapped[str | None] = mapped_column(String(16), nullable=True)
    date_of_birth: Mapped[date | None] = mapped_column(Date, nullable=True)
    credentials: Mapped[str | None] = mapped_column(String(64), nullable=True)
    specialty: Mapped[str | None] = mapped_column(String(64), nullable=True)
    sub_specialty: Mapped[str | None] = mapped_column(String(64), nullable=True)
    department: Mapped[str | None] = mapped_column(String(64), nullable=True)
    license_number: Mapped[str | None] = mapped_column(String(64), nullable=True)
    license_state: Mapped[str | None] = mapped_column(String(4), nullable=True)
    prompt_style: Mapped[str] = mapped_column(String(32), default="standard")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    encounters: Mapped[list["Encounter"]] = relationship("Encounter", back_populates="provider")
