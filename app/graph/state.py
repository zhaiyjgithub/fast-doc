"""EMR Graph State — single TypedDict shared across all LangGraph nodes."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from typing_extensions import TypedDict


class EMRGraphState(TypedDict, total=False):
    # Identifiers
    request_id: str
    encounter_id: str  # UUID as str
    patient_id: str  # UUID as str
    provider_id: str  # UUID as str

    # Provider context (pre-loaded for prompt construction)
    provider_specialty: str | None
    provider_sub_specialty: str | None
    provider_credentials: str | None
    provider_prompt_style: str  # "standard" | "concise" | "detailed" | "bullet"

    # Input data
    transcript: str
    patient_context: str  # Formatted patient history from PatientRAG

    # RAG results
    patient_chunks: list[dict[str, Any]]
    guideline_chunks: list[dict[str, Any]]

    # LLM outputs
    merged_context: str
    soap_note: dict[str, Any]  # Structured SOAP sections
    emr_text: str              # Final rendered EMR note

    # Coding
    icd_suggestions: list[dict[str, Any]]
    cpt_suggestions: list[dict[str, Any]]

    # Errors / routing
    errors: list[str]
    current_node: str
