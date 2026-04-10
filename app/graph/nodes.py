"""LangGraph node functions — each receives EMRGraphState, returns partial state."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import select

from app.graph.state import EMRGraphState
from app.models.providers import Provider
from app.services import llm_adapter  # noqa: F401 — imported here for patch-ability

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


# ---------------------------------------------------------------------------
# Node: load_provider_context
# ---------------------------------------------------------------------------

async def load_provider_context(
    state: EMRGraphState,
    *,
    db: "AsyncSession | None" = None,
) -> EMRGraphState:
    """Pre-load provider profile for prompt customisation."""
    provider_id = state.get("provider_id")
    if not provider_id or db is None:
        return {
            "provider_specialty": None,
            "provider_sub_specialty": None,
            "provider_credentials": None,
            "provider_prompt_style": state.get("provider_prompt_style", "standard"),
            "current_node": "load_provider_context",
        }

    try:
        result = await db.execute(select(Provider).where(Provider.id == uuid.UUID(provider_id)))
        provider = result.scalar_one_or_none()
    except Exception:
        provider = None

    return {
        "provider_specialty": provider.specialty if provider else None,
        "provider_sub_specialty": provider.sub_specialty if provider else None,
        "provider_credentials": provider.credentials if provider else None,
        "provider_prompt_style": provider.prompt_style if provider else "standard",
        "current_node": "load_provider_context",
    }


# ---------------------------------------------------------------------------
# Node: retrieve_patient_rag
# ---------------------------------------------------------------------------

async def retrieve_patient_rag(
    state: EMRGraphState,
    *,
    db: "AsyncSession | None" = None,
) -> EMRGraphState:
    """PatientRAG: semantic + keyword search over patient history."""
    if db is None:
        return {"patient_chunks": [], "current_node": "retrieve_patient_rag"}

    from app.services.patient_rag import PatientRAGService

    patient_id = state.get("patient_id")
    transcript = state.get("transcript", "")
    if not patient_id:
        return {"patient_chunks": [], "current_node": "retrieve_patient_rag"}

    svc = PatientRAGService(db)
    chunks = await svc.retrieve(
        query=transcript,
        patient_id=uuid.UUID(patient_id),
        top_k=5,
        request_id=state.get("request_id"),
    )
    return {"patient_chunks": chunks, "current_node": "retrieve_patient_rag"}


# ---------------------------------------------------------------------------
# Node: retrieve_guideline_rag
# ---------------------------------------------------------------------------

async def retrieve_guideline_rag(
    state: EMRGraphState,
    *,
    db: "AsyncSession | None" = None,
) -> EMRGraphState:
    """GuidelineRAG: semantic + keyword search over clinical guidelines."""
    if db is None:
        return {"guideline_chunks": [], "current_node": "retrieve_guideline_rag"}

    from app.services.guideline_rag import GuidelineRAGService

    transcript = state.get("transcript", "")
    svc = GuidelineRAGService(db)
    chunks = await svc.retrieve(
        query=transcript,
        top_k=5,
        request_id=state.get("request_id"),
    )
    return {"guideline_chunks": chunks, "current_node": "retrieve_guideline_rag"}


# ---------------------------------------------------------------------------
# Node: merge_context
# ---------------------------------------------------------------------------

async def merge_context(state: EMRGraphState) -> EMRGraphState:
    """Merge patient + guideline chunks into a single LLM context."""
    from app.services.emr_service import EMRService

    patient_text = "\n\n".join(c.get("chunk_text", "") for c in state.get("patient_chunks", []))
    guideline_text = "\n\n".join(c.get("chunk_text", "") for c in state.get("guideline_chunks", []))

    parts = []
    if patient_text:
        parts.append(f"### Relevant Patient History\n{patient_text}")
    if guideline_text:
        parts.append(f"### Relevant Guidelines\n{guideline_text}")

    return {
        "merged_context": "\n\n".join(parts),
        "current_node": "merge_context",
    }


# ---------------------------------------------------------------------------
# Node: generate_emr
# ---------------------------------------------------------------------------

async def generate_emr(
    state: EMRGraphState,
    *,
    db: "AsyncSession | None" = None,
) -> EMRGraphState:
    """Call Qwen to generate the SOAP note from the merged context."""
    from app.services.emr_service import EMRService, build_system_prompt
    from app.core.security import redact_phi

    transcript = state.get("transcript", "")
    merged_context = state.get("merged_context", "")

    system_prompt = build_system_prompt(
        specialty=state.get("provider_specialty"),
        sub_specialty=state.get("provider_sub_specialty"),
        credentials=state.get("provider_credentials"),
        prompt_style=state.get("provider_prompt_style", "standard"),
    )

    redacted = redact_phi(transcript)
    user_message = (
        f"## Encounter Transcript\n{redacted}\n\n"
        f"## Clinical Context\n{merged_context}\n\n"
        "Generate a SOAP note as JSON."
    )

    raw = await llm_adapter.chat(
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        db=db,
        request_id=state.get("request_id"),
        node_name="generate_emr",
    )

    soap_note = EMRService._parse_soap(raw)
    emr_text = EMRService._render_emr(soap_note)

    return {
        "soap_note": soap_note,
        "emr_text": emr_text,
        "current_node": "generate_emr",
    }


# ---------------------------------------------------------------------------
# Node: suggest_codes
# ---------------------------------------------------------------------------

async def suggest_codes(
    state: EMRGraphState,
    *,
    db: "AsyncSession | None" = None,
) -> EMRGraphState:
    """ICD/CPT auto-coding via CodingService."""
    if db is None:
        return {
            "icd_suggestions": [],
            "cpt_suggestions": [],
            "current_node": "suggest_codes",
        }

    from app.services.coding_service import CodingService

    soap_note = state.get("soap_note", {})
    emr_text = state.get("emr_text", "")
    request_id = state.get("request_id")

    coding_svc = CodingService(db)
    icd_suggestions = await coding_svc.suggest_icd(
        soap_note=soap_note,
        emr_text=emr_text,
        request_id=request_id,
    )
    cpt_suggestions = await coding_svc.suggest_cpt(
        soap_note=soap_note,
        emr_text=emr_text,
        request_id=request_id,
    )

    return {
        "icd_suggestions": icd_suggestions,
        "cpt_suggestions": cpt_suggestions,
        "current_node": "suggest_codes",
    }
