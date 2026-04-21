"""EMRService — orchestrates DualRAG + provider-aware LLM prompt to generate a SOAP note.

Provider-Aware Prompt Construction:
  Specialty → general system prefix
  Sub-specialty → supplementary instruction
  prompt_style → response format modifier
  credentials → addressed in preamble
"""

from __future__ import annotations

import json
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import select

from app.core.security import redact_phi
from app.graph.state import EMRGraphState
from app.models.providers import Provider
from app.models.clinical import Encounter
from app.services import llm_adapter
from app.services.guideline_rag import GuidelineRAGService
from app.services.patient_rag import PatientRAGService

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

# ---------------------------------------------------------------------------
# Provider-aware prompt constants
# ---------------------------------------------------------------------------

SPECIALTY_PROMPT_PREFIXES: dict[str, str] = {
    "pulmonology": (
        "You are a clinical documentation assistant for a pulmonologist. "
        "Emphasise respiratory function, spirometry values, and inhaler adherence."
    ),
    "cardiology": (
        "You are a clinical documentation assistant for a cardiologist. "
        "Emphasise cardiovascular findings, ECG interpretation, and haemodynamic status."
    ),
    "internal_medicine": (
        "You are a clinical documentation assistant for an internal medicine physician. "
        "Provide a comprehensive, systems-based assessment."
    ),
}
_DEFAULT_SPECIALTY_PREFIX = (
    "You are an expert clinical documentation assistant. "
    "Generate accurate, evidence-based EMR notes."
)

SUB_SPECIALTY_ADDITIONS: dict[str, str] = {
    "critical_care": (
        "Pay special attention to ventilator settings, vasopressor requirements, "
        "fluid balance, and organ function."
    ),
    "interventional": (
        "Document procedural findings, pre/post-procedure status, and complications."
    ),
    "sleep_medicine": (
        "Include sleep study findings, AHI, CPAP/BiPAP compliance, and daytime symptoms."
    ),
}

PROMPT_STYLE_INSTRUCTIONS: dict[str, str] = {
    "standard": "Write in standard clinical prose. Use complete sentences.",
    "concise": "Be concise. Use brief sentences and avoid repetition.",
    "detailed": (
        "Be thorough and detailed. Include all relevant clinical reasoning, "
        "differentials, and evidence-based references."
    ),
    "bullet": "Use structured bullet points for each SOAP section.",
}


def build_system_prompt(
    *,
    specialty: str | None,
    sub_specialty: str | None,
    credentials: str | None,
    prompt_style: str,
) -> str:
    prefix = SPECIALTY_PROMPT_PREFIXES.get(
        (specialty or "").lower().replace(" ", "_"), _DEFAULT_SPECIALTY_PREFIX
    )
    sub_add = SUB_SPECIALTY_ADDITIONS.get((sub_specialty or "").lower().replace(" ", "_"), "")
    style = PROMPT_STYLE_INSTRUCTIONS.get(prompt_style, PROMPT_STYLE_INSTRUCTIONS["standard"])

    parts = [prefix]
    if sub_add:
        parts.append(sub_add)
    parts.append(style)
    parts.append(
        "The patient transcript may be in any language. "
        "Always respond entirely in English regardless of the input language. "
        'Always return your response as valid JSON with keys: '
        '"subjective", "objective", "assessment", "plan".'
    )
    return " ".join(parts)


# ---------------------------------------------------------------------------
# EMR Service
# ---------------------------------------------------------------------------

class EMRService:
    def __init__(self, db: "AsyncSession") -> None:
        self.db = db

    async def generate(
        self,
        *,
        encounter_id: str,
        patient_id: str,
        provider_id: str | None = None,
        transcript: str,
        request_id: str | None = None,
        top_k_patient: int = 5,
        top_k_guideline: int = 5,
        conversation_duration_seconds: int | None = None,
    ) -> EMRGraphState:
        """Run the full DualRAG + EMR generation pipeline."""
        patient_uuid = uuid.UUID(patient_id)
        encounter_uuid = uuid.UUID(encounter_id)
        encounter = await self._load_encounter_by_uuid(encounter_uuid)
        if encounter is not None:
            encounter.transcript_text = transcript

        # 1. Load provider context
        provider = await self._load_provider(provider_id)

        # 2. Patient RAG
        patient_rag = PatientRAGService(self.db)
        patient_chunks = await patient_rag.retrieve(
            query=transcript,
            patient_id=patient_uuid,
            top_k=top_k_patient,
            request_id=request_id,
        )

        # 3. Guideline RAG
        guideline_rag = GuidelineRAGService(self.db)
        guideline_chunks = await guideline_rag.retrieve(
            query=transcript,
            top_k=top_k_guideline,
            request_id=request_id,
        )

        # 4. Merge context
        merged_context = self._merge_context(patient_chunks, guideline_chunks)

        # 5. Build provider-aware prompt
        system_prompt = build_system_prompt(
            specialty=provider.specialty if provider else None,
            sub_specialty=provider.sub_specialty if provider else None,
            credentials=provider.credentials if provider else None,
            prompt_style=provider.prompt_style if provider else "standard",
        )

        # 6. Generate SOAP note
        redacted_transcript = redact_phi(transcript)
        user_message = (
            f"## Encounter Transcript\n{redacted_transcript}\n\n"
            f"## Clinical Context\n{merged_context}\n\n"
            "Generate a SOAP note for this encounter as JSON."
        )

        soap_json_text = await llm_adapter.chat(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            db=self.db,
            request_id=request_id,
            node_name="generate_emr",
        )

        # 7. Parse SOAP JSON
        soap_note = self._parse_soap(soap_json_text)
        emr_text = self._render_emr(soap_note)

        # 8. Persist EmrNote
        from app.models.clinical import EmrNote
        emr_note = EmrNote(
            encounter_id=encounter_uuid,
            request_id=request_id,
            soap_json=soap_note,
            note_text=emr_text,
            conversation_duration_seconds=conversation_duration_seconds,
            context_trace_json={
                "provider_id": str(provider.id) if provider else None,
                "provider_specialty": provider.specialty if provider else None,
                "provider_sub_specialty": provider.sub_specialty if provider else None,
                "provider_prompt_style": provider.prompt_style if provider else "standard",
                "patient_chunks_retrieved": len(patient_chunks),
                "guideline_chunks_retrieved": len(guideline_chunks),
            },
            is_final=False,
            version=1,
        )
        self.db.add(emr_note)
        await self.db.flush()

        # 9. Update encounter chief complaint from current transcript
        await self._upsert_encounter_chief_complaint_from_transcript(
            encounter=encounter,
            transcript=transcript,
            request_id=request_id,
        )

        # 10. ICD / CPT auto-coding
        from app.services.coding_service import CodingService
        coding_svc = CodingService(self.db)
        icd_suggestions = await coding_svc.suggest_icd(
            encounter_id=str(encounter_uuid),
            soap_note=soap_note,
            emr_text=emr_text,
            request_id=request_id,
        )
        cpt_suggestions = await coding_svc.suggest_cpt(
            encounter_id=str(encounter_uuid),
            soap_note=soap_note,
            emr_text=emr_text,
            request_id=request_id,
        )
        if encounter is not None:
            encounter.status = "done"
            await self.db.flush()

        return EMRGraphState(
            request_id=request_id or "",
            encounter_id=str(encounter_uuid),
            patient_id=patient_id,
            provider_id=str(provider.id) if provider else "",
            provider_specialty=provider.specialty if provider else None,
            provider_sub_specialty=provider.sub_specialty if provider else None,
            provider_credentials=provider.credentials if provider else None,
            provider_prompt_style=provider.prompt_style if provider else "standard",
            transcript=transcript,
            patient_chunks=patient_chunks,
            guideline_chunks=guideline_chunks,
            merged_context=merged_context,
            soap_note=soap_note,
            emr_text=emr_text,
            icd_suggestions=icd_suggestions,
            cpt_suggestions=cpt_suggestions,
            errors=[],
            current_node="generate_emr",
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _load_provider(self, provider_id: str | None) -> Provider | None:
        if not provider_id:
            return None
        try:
            provider_uuid = uuid.UUID(provider_id)
        except ValueError:
            return None
        result = await self.db.execute(
            select(Provider).where(Provider.id == provider_uuid)
        )
        return result.scalar_one_or_none()

    async def _load_encounter_by_uuid(self, encounter_uuid: uuid.UUID) -> Encounter | None:
        result = await self.db.execute(
            select(Encounter).where(Encounter.id == encounter_uuid)
        )
        return result.scalar_one_or_none()

    async def _upsert_encounter_chief_complaint_from_transcript(
        self,
        *,
        encounter: Encounter | None,
        transcript: str,
        request_id: str | None = None,
    ) -> None:
        if encounter is None:
            return

        chief_complaint = await self._summarize_chief_complaint_from_transcript(
            transcript=transcript,
            request_id=request_id,
        )
        encounter.chief_complaint = chief_complaint
        await self.db.flush()

    async def _summarize_chief_complaint_from_transcript(
        self,
        *,
        transcript: str,
        request_id: str | None = None,
    ) -> str:
        redacted_transcript = redact_phi(transcript).strip()
        if not redacted_transcript:
            return ""
        fallback = self._fallback_chief_complaint(redacted_transcript)

        try:
            summary = await llm_adapter.chat(
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You summarize a clinical encounter transcript into a concise chief complaint. "
                            "Return plain text only (no JSON), max 12 words, no punctuation at the end."
                        ),
                    },
                    {
                        "role": "user",
                        "content": f"Transcript:\n{redacted_transcript}\n\nChief complaint:",
                    },
                ],
                db=self.db,
                request_id=request_id,
                node_name="summarize_chief_complaint",
            )
            cleaned = self._clean_chief_complaint_text(summary)
            return cleaned or fallback
        except Exception:
            return fallback

    @staticmethod
    def _clean_chief_complaint_text(raw: str | None) -> str:
        if not raw:
            return ""
        text = raw.strip().splitlines()[0].strip()
        if text.startswith('"') and text.endswith('"') and len(text) >= 2:
            text = text[1:-1].strip()
        if text.startswith("'") and text.endswith("'") and len(text) >= 2:
            text = text[1:-1].strip()
        return text.rstrip(" .,:;")

    @staticmethod
    def _fallback_chief_complaint(transcript: str) -> str:
        first_line = transcript.splitlines()[0].strip()
        if not first_line:
            return ""
        return first_line[:120].rstrip(" .,:;")

    @staticmethod
    def _merge_context(
        patient_chunks: list[dict], guideline_chunks: list[dict]
    ) -> str:
        patient_text = "\n\n".join(
            c["chunk_text"] for c in patient_chunks[:5]
        )
        guideline_text = "\n\n".join(
            c["chunk_text"] for c in guideline_chunks[:5]
        )
        parts = []
        if patient_text:
            parts.append(f"### Relevant Patient History\n{patient_text}")
        if guideline_text:
            parts.append(f"### Relevant Guidelines\n{guideline_text}")
        return "\n\n".join(parts)

    @staticmethod
    def _parse_soap(raw_text: str) -> dict:
        """Extract JSON from raw LLM output (may be wrapped in markdown code blocks)."""
        import re

        def _to_str(val: object) -> str:
            """Coerce any value to a plain string."""
            if isinstance(val, str):
                return val
            if isinstance(val, dict):
                # e.g. {"findings": "...", "impression": "..."} → joined prose
                return " ".join(str(v) for v in val.values())
            if isinstance(val, list):
                return " ".join(str(v) for v in val)
            return str(val) if val is not None else ""

        # Strip markdown code fences
        text = re.sub(r"```(?:json)?\s*", "", raw_text).strip().rstrip("`").strip()
        try:
            data = json.loads(text)
            return {
                "subjective": _to_str(data.get("subjective", "")),
                "objective":  _to_str(data.get("objective", "")),
                "assessment": _to_str(data.get("assessment", "")),
                "plan":       _to_str(data.get("plan", "")),
            }
        except json.JSONDecodeError:
            return {
                "subjective": raw_text,
                "objective":  "",
                "assessment": "",
                "plan":       "",
            }

    @staticmethod
    def _render_emr(soap_note: dict) -> str:
        sections = [
            ("SUBJECTIVE", soap_note.get("subjective", "")),
            ("OBJECTIVE", soap_note.get("objective", "")),
            ("ASSESSMENT", soap_note.get("assessment", "")),
            ("PLAN", soap_note.get("plan", "")),
        ]
        lines = []
        for heading, content in sections:
            if content:
                lines.append(f"**{heading}**\n{content}")
        return "\n\n".join(lines)
