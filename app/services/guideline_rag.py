"""GuidelineRAG — Hybrid Semantic + Keyword retrieval for clinical guideline chunks.

Unlike PatientRAG, guideline chunks are NOT filtered by patient_id.
Uses the same RRF merge strategy.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from sqlalchemy import text

from app.models.rag import RetrievalLog
from app.services import llm_adapter
from app.services.patient_rag import PatientRAGService  # reuse RRF helper

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

_CANDIDATE_K = 20


class GuidelineRAGService:
    def __init__(self, db: "AsyncSession") -> None:
        self.db = db

    async def retrieve(
        self,
        *,
        query: str,
        top_k: int = 5,
        request_id: str | None = None,
    ) -> list[dict]:
        """Return top-k guideline chunks merged via RRF."""
        start = time.monotonic()

        vectors = await llm_adapter.embed([query], request_id=request_id)
        query_vector = vectors[0]

        semantic_rows = await self._semantic_search(query_vector, _CANDIDATE_K)
        keyword_rows = await self._keyword_search(query, _CANDIDATE_K)

        merged = PatientRAGService._rrf_merge(semantic_rows, keyword_rows, top_k=top_k)

        latency_ms = int((time.monotonic() - start) * 1000)
        await self._log(
            request_id=request_id,
            query_text=query,
            top_k=top_k,
            result_count=len(merged),
            latency_ms=latency_ms,
        )
        return merged

    # ------------------------------------------------------------------
    # Sub-retrievals
    # ------------------------------------------------------------------

    async def _semantic_search(self, query_vector: list[float], k: int) -> list[dict]:
        vec_literal = "[" + ",".join(str(v) for v in query_vector) + "]"
        sql = text(
            """
            SELECT kc.id, kc.chunk_text, kc.chunk_index, kc.metadata_json,
                   kc.embedding_vector <=> CAST(:vec AS vector) AS distance
            FROM knowledge_chunks kc
            JOIN knowledge_documents kd ON kc.document_id = kd.id
            WHERE kd.source_namespace = 'guideline'
              AND kd.is_active = true
              AND kc.is_active = true
              AND kc.embedding_vector IS NOT NULL
            ORDER BY distance ASC
            LIMIT :k
            """
        )
        result = await self.db.execute(sql, {"vec": vec_literal, "k": k})
        return [
            {
                "chunk_id": str(row.id),
                "chunk_text": row.chunk_text,
                "chunk_index": row.chunk_index,
                "metadata_json": row.metadata_json,
                "score": float(row.distance),
            }
            for row in result.fetchall()
        ]

    async def _keyword_search(self, query: str, k: int) -> list[dict]:
        keywords = [w.strip() for w in query.split() if len(w.strip()) >= 3]
        if not keywords:
            return []

        conditions = " OR ".join(f"kc.chunk_text ILIKE :kw{i}" for i in range(len(keywords)))
        params: dict = {"k": k}
        for i, kw in enumerate(keywords):
            params[f"kw{i}"] = f"%{kw}%"

        sql = text(
            f"""
            SELECT kc.id, kc.chunk_text, kc.chunk_index, kc.metadata_json
            FROM knowledge_chunks kc
            JOIN knowledge_documents kd ON kc.document_id = kd.id
            WHERE kd.source_namespace = 'guideline'
              AND kd.is_active = true
              AND kc.is_active = true
              AND ({conditions})
            ORDER BY kc.created_at DESC
            LIMIT :k
            """
        )
        result = await self.db.execute(sql, params)
        return [
            {
                "chunk_id": str(row.id),
                "chunk_text": row.chunk_text,
                "chunk_index": row.chunk_index,
                "metadata_json": row.metadata_json,
                "score": 0.0,
            }
            for row in result.fetchall()
        ]

    async def _log(
        self,
        *,
        request_id: str | None,
        query_text: str,
        top_k: int,
        result_count: int,
        latency_ms: int,
    ) -> None:
        record = RetrievalLog(
            request_id=request_id,
            retrieval_type="guideline",
            query_text=query_text,
            top_k=top_k,
            result_count=result_count,
            latency_ms=latency_ms,
        )
        self.db.add(record)
        await self.db.flush()
