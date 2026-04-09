"""AuditService — write immutable audit events to ``audit_events`` table.

All PHI access and AI generation events must be logged here.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.models.ops import AuditEvent

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class AuditService:
    def __init__(self, db: "AsyncSession") -> None:
        self.db = db

    async def log(
        self,
        *,
        event_type: str,
        actor_id: str | None = None,
        actor_role: str | None = None,
        patient_id: str | None = None,
        request_id: str | None = None,
        access_reason: str | None = None,
        event_data: dict | None = None,
    ) -> AuditEvent:
        """Write a single audit event; flushes to the session (caller commits)."""
        event = AuditEvent(
            event_type=event_type,
            actor_id=actor_id,
            actor_role=actor_role,
            patient_id=patient_id,
            request_id=request_id,
            access_reason=access_reason,
            event_data=event_data,
        )
        self.db.add(event)
        await self.db.flush()
        return event


# Convenience event types
class EventType:
    EMR_GENERATED = "emr.generated"
    EMR_VIEWED = "emr.viewed"
    PATIENT_RAG_ACCESSED = "patient_rag.accessed"
    GUIDELINE_RAG_ACCESSED = "guideline_rag.accessed"
    PHI_ACCESSED = "phi.accessed"
    CODING_SUGGESTED = "coding.suggested"
    DOCUMENT_INGESTED = "document.ingested"
    LOGIN = "auth.login"
    LOGOUT = "auth.logout"
