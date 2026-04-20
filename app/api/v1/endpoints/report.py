"""GET /v1/encounters/{encounter_id}/report — aggregate encounter report."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import CurrentPrincipal, get_current_user
from app.db.session import get_db
from app.models.clinical import EmrNote
from app.models.coding import CodingEvidenceLink, CodingSuggestion

router = APIRouter(prefix="/encounters", tags=["report"])


class EvidenceItem(BaseModel):
    evidence_route: str | None
    excerpt: str | None


class CodeSuggestionItem(BaseModel):
    code: str
    code_type: str
    rank: int
    condition: str | None = None
    description: str | None = None
    confidence: float | None
    rationale: str | None
    status: str
    evidence: list[EvidenceItem] = []


class SOAPNote(BaseModel):
    subjective: str = ""
    objective: str = ""
    assessment: str = ""
    plan: str = ""


class EMRSummary(BaseModel):
    note_id: str
    soap_note: SOAPNote
    note_text: str | None
    is_final: bool
    request_id: str | None
    conversation_duration_seconds: int | None = None


class EncounterReport(BaseModel):
    encounter_id: str
    emr: EMRSummary | None
    icd_suggestions: list[CodeSuggestionItem] = []
    cpt_suggestions: list[CodeSuggestionItem] = []
    generated_at: str | None = None


@router.get("/{encounter_id}/report", response_model=EncounterReport)
async def get_encounter_report(
    encounter_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _user: Annotated[CurrentPrincipal, Depends(get_current_user)],
) -> EncounterReport:
    """Return the latest EMR note and coding suggestions for an encounter."""

    # Latest EMR note
    note_row = await db.execute(
        select(EmrNote)
        .where(EmrNote.encounter_id == encounter_id)
        .order_by(EmrNote.created_at.desc())
        .limit(1)
    )
    note: EmrNote | None = note_row.scalars().first()

    if note is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No EMR note found for encounter {encounter_id}",
        )

    # Coding suggestions for this encounter
    sugg_rows = await db.execute(
        select(CodingSuggestion)
        .where(CodingSuggestion.encounter_id == encounter_id)
        .order_by(CodingSuggestion.code_type, CodingSuggestion.rank)
    )
    suggestions = sugg_rows.scalars().all()

    # Evidence links for all suggestions
    sugg_ids = [s.id for s in suggestions]
    evidence_map: dict[str, list[CodingEvidenceLink]] = {}
    if sugg_ids:
        ev_rows = await db.execute(
            select(CodingEvidenceLink).where(CodingEvidenceLink.suggestion_id.in_(sugg_ids))
        )
        for ev in ev_rows.scalars().all():
            key = str(ev.suggestion_id)
            evidence_map.setdefault(key, []).append(ev)

    icd_list: list[CodeSuggestionItem] = []
    cpt_list: list[CodeSuggestionItem] = []
    for s in suggestions:
        ev_items = [
            EvidenceItem(evidence_route=e.evidence_route, excerpt=e.excerpt)
            for e in evidence_map.get(str(s.id), [])
        ]
        item = CodeSuggestionItem(
            code=s.code,
            code_type=s.code_type,
            rank=s.rank,
            condition=s.condition,
            description=s.description,
            confidence=float(s.confidence) if s.confidence is not None else None,
            rationale=s.rationale,
            status=s.status,
            evidence=ev_items,
        )
        if s.code_type == "ICD":
            icd_list.append(item)
        else:
            cpt_list.append(item)

    soap_dict = note.soap_json or {}
    emr_summary = EMRSummary(
        note_id=str(note.id),
        soap_note=SOAPNote(
            subjective=soap_dict.get("subjective", ""),
            objective=soap_dict.get("objective", ""),
            assessment=soap_dict.get("assessment", ""),
            plan=soap_dict.get("plan", ""),
        ),
        note_text=note.note_text,
        is_final=note.is_final,
        request_id=note.request_id,
        conversation_duration_seconds=note.conversation_duration_seconds,
    )

    return EncounterReport(
        encounter_id=encounter_id,
        emr=emr_summary,
        icd_suggestions=icd_list,
        cpt_suggestions=cpt_list,
        generated_at=note.created_at.isoformat() if note.created_at else None,
    )
