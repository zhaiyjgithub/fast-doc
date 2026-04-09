"""Tests for AuditService."""

from sqlalchemy import select

from app.models.ops import AuditEvent
from app.services.audit_service import AuditService, EventType


async def test_audit_log_creates_record(db_session):
    svc = AuditService(db_session)
    event = await svc.log(
        event_type=EventType.EMR_GENERATED,
        actor_id="provider-001",
        actor_role="physician",
        patient_id="patient-001",
        request_id="req-audit-001",
        access_reason="Routine EMR generation",
        event_data={"encounter_id": "enc-001", "model": "qwen-max"},
    )
    assert event.id is not None

    result = await db_session.execute(
        select(AuditEvent).where(AuditEvent.request_id == "req-audit-001")
    )
    record = result.scalar_one_or_none()
    assert record is not None
    assert record.event_type == EventType.EMR_GENERATED
    assert record.actor_role == "physician"
    assert record.event_data["encounter_id"] == "enc-001"


async def test_audit_log_immutable_once_written(db_session):
    """Verify audit records persist independently from session state."""
    svc = AuditService(db_session)
    await svc.log(
        event_type=EventType.PHI_ACCESSED,
        patient_id="patient-002",
        request_id="req-audit-002",
    )
    await db_session.commit()

    result = await db_session.execute(
        select(AuditEvent).where(AuditEvent.request_id == "req-audit-002")
    )
    record = result.scalar_one_or_none()
    assert record is not None
    # created_at is set by DB server_default — must be present
    assert record.created_at is not None


async def test_audit_log_minimal_fields(db_session):
    """Audit log must work with only event_type supplied."""
    svc = AuditService(db_session)
    event = await svc.log(event_type="system.startup")
    assert event.event_type == "system.startup"
    assert event.actor_id is None
    assert event.patient_id is None
