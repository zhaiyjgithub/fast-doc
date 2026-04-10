"""CodingService — LLM-assisted ICD-10-CM and CPT code suggestion.

Pipeline:
  1. keyword_extractor: extract clinical keywords from EMR SOAP note
  2. catalog_search: SQL pre-filter using ILIKE keyword matching
  3. LLM ranker: Qwen selects top codes with confidence + rationale
  4. rule_engine: post-LLM validation (code format check, etc.)
  5. persist: write CodingSuggestion + CodingEvidenceLink rows
"""

from __future__ import annotations

import json
import re
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import text

from app.services import llm_adapter

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

_MAX_CATALOG_CANDIDATES = 20


class CodingService:
    def __init__(self, db: "AsyncSession") -> None:
        self.db = db

    async def suggest_icd(
        self,
        *,
        encounter_id: str,
        soap_note: dict,
        emr_text: str,
        request_id: str | None = None,
        top_k: int = 5,
    ) -> list[dict]:
        """Return top-k ICD-10-CM code suggestions with confidence and rationale."""
        keywords = self._extract_keywords(soap_note, emr_text)
        candidates = await self._search_icd_catalog(keywords)
        if not candidates:
            return []
        suggestions = await self._rank_codes(
            code_type="ICD",
            candidates=candidates,
            soap_note=soap_note,
            emr_text=emr_text,
            request_id=request_id,
            top_k=top_k,
        )
        await self._persist_suggestions(suggestions, "ICD", encounter_id, request_id)
        return suggestions

    async def suggest_cpt(
        self,
        *,
        encounter_id: str,
        soap_note: dict,
        emr_text: str,
        request_id: str | None = None,
        top_k: int = 5,
    ) -> list[dict]:
        """Return top-k CPT code suggestions with confidence and rationale."""
        keywords = self._extract_keywords(soap_note, emr_text)
        candidates = await self._search_cpt_catalog(keywords)
        if not candidates:
            return []
        suggestions = await self._rank_codes(
            code_type="CPT",
            candidates=candidates,
            soap_note=soap_note,
            emr_text=emr_text,
            request_id=request_id,
            top_k=top_k,
        )
        await self._persist_suggestions(suggestions, "CPT", encounter_id, request_id)
        return suggestions

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    async def _persist_suggestions(
        self,
        suggestions: list[dict],
        code_type: str,
        encounter_id: str,
        request_id: str | None,
    ) -> None:
        """Write CodingSuggestion + CodingEvidenceLink rows for each suggestion."""
        from app.models.coding import CodingEvidenceLink, CodingSuggestion

        enc_uuid = uuid.UUID(encounter_id)
        for rank, s in enumerate(suggestions, start=1):
            suggestion = CodingSuggestion(
                encounter_id=enc_uuid,
                request_id=request_id,
                code_type=code_type,
                code=s["code"],
                rank=rank,
                confidence=s["confidence"],
                rationale=s["rationale"],
                status="needs_review",
            )
            self.db.add(suggestion)
            await self.db.flush()

            evidence = CodingEvidenceLink(
                suggestion_id=suggestion.id,
                evidence_route=f"llm_{code_type.lower()}",
                chunk_id=None,
                excerpt=s["rationale"][:500] if s.get("rationale") else None,
            )
            self.db.add(evidence)
            await self.db.flush()

    # ------------------------------------------------------------------
    # Keyword extraction (non-LLM, deterministic)
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_keywords(soap_note: dict, emr_text: str) -> list[str]:
        """Extract clinical terms from SOAP sections."""
        def _safe_str(val: object) -> str:
            if isinstance(val, str):
                return val
            if isinstance(val, (dict, list)):
                return json.dumps(val)
            return str(val) if val is not None else ""

        text_parts = [
            _safe_str(soap_note.get("assessment", "")),
            _safe_str(soap_note.get("plan", "")),
            _safe_str(soap_note.get("objective", "")),
        ]
        combined = " ".join(text_parts)
        # Simple tokenisation: words ≥4 chars that are not stop words
        stopwords = {
            "with", "that", "this", "have", "from", "will", "been", "were",
            "they", "their", "also", "patient", "therapy", "treatment",
            "including", "using", "based", "clinical", "should", "return",
            "recommend", "evidence", "care", "each", "note", "week",
        }
        tokens = re.findall(r"\b[a-zA-Z]{4,}\b", combined)
        seen: set[str] = set()
        keywords: list[str] = []
        for tok in tokens:
            lower = tok.lower()
            if lower not in stopwords and lower not in seen:
                seen.add(lower)
                keywords.append(lower)
            if len(keywords) >= 15:
                break
        return keywords

    # ------------------------------------------------------------------
    # Catalog search
    # ------------------------------------------------------------------

    async def _search_icd_catalog(self, keywords: list[str]) -> list[dict]:
        if not keywords:
            return []
        conditions = " OR ".join(
            f"(description ILIKE :kw{i} OR code ILIKE :kw{i})" for i in range(len(keywords))
        )
        params: dict = {"k": _MAX_CATALOG_CANDIDATES}
        for i, kw in enumerate(keywords):
            params[f"kw{i}"] = f"%{kw}%"

        sql = text(
            f"SELECT code, description FROM icd_catalog WHERE {conditions} LIMIT :k"
        )
        result = await self.db.execute(sql, params)
        return [{"code": r.code, "description": r.description} for r in result.fetchall()]

    async def _search_cpt_catalog(self, keywords: list[str]) -> list[dict]:
        if not keywords:
            return []
        conditions = " OR ".join(
            f"(description ILIKE :kw{i} OR short_name ILIKE :kw{i})" for i in range(len(keywords))
        )
        params: dict = {"k": _MAX_CATALOG_CANDIDATES}
        for i, kw in enumerate(keywords):
            params[f"kw{i}"] = f"%{kw}%"

        sql = text(
            f"SELECT code, short_name, description FROM cpt_catalog WHERE {conditions} LIMIT :k"
        )
        result = await self.db.execute(sql, params)
        return [
            {"code": r.code, "description": r.description or r.short_name}
            for r in result.fetchall()
        ]

    # ------------------------------------------------------------------
    # LLM ranker
    # ------------------------------------------------------------------

    async def _rank_codes(
        self,
        *,
        code_type: str,
        candidates: list[dict],
        soap_note: dict,
        emr_text: str,
        request_id: str | None,
        top_k: int,
    ) -> list[dict]:
        candidate_text = "\n".join(
            f"  {c['code']}: {c['description']}" for c in candidates[:_MAX_CATALOG_CANDIDATES]
        )
        system = (
            f"You are a medical coding specialist. Given a clinical SOAP note and a list of "
            f"{code_type} code candidates, select the most appropriate codes. "
            "Always respond in English. "
            "Return JSON array of objects with keys: code, confidence (0-1), rationale."
        )
        user = (
            f"## SOAP Assessment\n{soap_note.get('assessment', '')}\n\n"
            f"## SOAP Plan\n{soap_note.get('plan', '')}\n\n"
            f"## Candidate {code_type} codes\n{candidate_text}\n\n"
            f"Select top {top_k} most appropriate codes. Return only JSON array."
        )

        raw = await llm_adapter.chat(
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            db=self.db,
            request_id=request_id,
            node_name=f"suggest_{code_type.lower()}",
        )

        suggestions = self._parse_code_suggestions(raw)
        return self._apply_rule_engine(suggestions, code_type)[:top_k]

    # ------------------------------------------------------------------
    # Response parsing
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_code_suggestions(raw: str) -> list[dict]:
        text = re.sub(r"```(?:json)?\s*", "", raw).strip().rstrip("`").strip()
        try:
            data = json.loads(text)
            if isinstance(data, list):
                return data
            return []
        except json.JSONDecodeError:
            return []

    # ------------------------------------------------------------------
    # Rule engine — deterministic post-LLM validation
    # ------------------------------------------------------------------

    @staticmethod
    def _apply_rule_engine(suggestions: list[dict], code_type: str) -> list[dict]:
        valid = []
        for s in suggestions:
            code = str(s.get("code", "")).strip()
            if code_type == "ICD":
                # ICD-10-CM: letter + 2 digits + optional decimal + up to 4 alphanumeric
                if not re.match(r"^[A-Z]\d{2}\.?[\w]{0,4}$", code, re.IGNORECASE):
                    continue
            elif code_type == "CPT":
                # CPT: 4-5 alphanumeric chars (covers standard 5-digit and category-II/III codes)
                if not re.match(r"^[\dA-Z]{4,5}$", code, re.IGNORECASE):
                    continue
            try:
                conf = float(s.get("confidence", 0))
                conf = max(0.0, min(1.0, conf))
            except (ValueError, TypeError):
                conf = 0.0

            valid.append(
                {
                    "code": code.upper(),
                    "confidence": conf,
                    "rationale": str(s.get("rationale", "")),
                    "status": "needs_review",
                }
            )
        return valid
