import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base


class IcdCatalog(Base):
    __tablename__ = "icd_catalog"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(16), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    chapter: Mapped[str | None] = mapped_column(String(8), nullable=True)
    catalog_version: Mapped[str] = mapped_column(String(32), nullable=False)
    effective_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CptCatalog(Base):
    __tablename__ = "cpt_catalog"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(16), nullable=False)
    short_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    avg_fee: Mapped[float | None] = mapped_column(Numeric(10, 4), nullable=True)
    rvu: Mapped[float | None] = mapped_column(Numeric(8, 4), nullable=True)
    catalog_version: Mapped[str] = mapped_column(String(32), nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CodingSuggestion(Base):
    __tablename__ = "coding_suggestions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    encounter_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("encounters.id"), nullable=False
    )
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    code_type: Mapped[str] = mapped_column(String(8), nullable=False)  # "ICD" | "CPT"
    code: Mapped[str] = mapped_column(String(16), nullable=False)
    rank: Mapped[int] = mapped_column(default=1)
    confidence: Mapped[float | None] = mapped_column(Numeric(4, 3), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    condition: Mapped[str | None] = mapped_column(Text, nullable=True)
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="needs_review")
    page: Mapped[int | None] = mapped_column(nullable=True)
    modifier_hint: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    evidence_links: Mapped[list["CodingEvidenceLink"]] = relationship(
        "CodingEvidenceLink", back_populates="suggestion"
    )


class CodingEvidenceLink(Base):
    __tablename__ = "coding_evidence_links"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    suggestion_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("coding_suggestions.id"), nullable=False
    )
    evidence_route: Mapped[str | None] = mapped_column(String(32), nullable=True)  # "patient_rag" | "guideline_rag"
    chunk_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    excerpt: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    suggestion: Mapped["CodingSuggestion"] = relationship("CodingSuggestion", back_populates="evidence_links")
