"""PatientRAG — Hybrid Semantic + Keyword retrieval for patient history chunks.

Retrieval strategy:
  1. Semantic: cosine similarity over ``embedding_vector`` (pgvector)
  2. Keyword: BM25-style ILIKE match on ``chunk_text``
  3. RRF (Reciprocal Rank Fusion): merge both result sets by rank
"""

from __future__ import annotations

import time
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import text

from app.models.rag import RetrievalLog
from app.services import llm_adapter

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

# Number of candidates fetched per sub-retrieval before RRF merge
_CANDIDATE_K = 20
_RRF_K_CONST = 60  # RRF damping constant


class PatientRAGService:
    def __init__(self, db: "AsyncSession") -> None:
        self.db = db

    async def retrieve(
        self,
        *,
        query: str,
        patient_id: uuid.UUID,
        top_k: int = 5,
        request_id: str | None = None,
    ) -> list[dict]:
        """Return top-k chunks for the patient, merged via RRF.

        Each result dict contains:
          - chunk_id, chunk_text, chunk_index, metadata_json, rrf_score
        """
        start = time.monotonic()

        # Embed the query
        vectors = await llm_adapter.embed([query], request_id=request_id)
        query_vector = vectors[0]

        semantic_rows = await self._semantic_search(query_vector, patient_id, _CANDIDATE_K)
        keyword_rows = await self._keyword_search(query, patient_id, _CANDIDATE_K)

        merged = self._rrf_merge(semantic_rows, keyword_rows, top_k=top_k)

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

    async def _semantic_search(
        self, query_vector: list[float], patient_id: uuid.UUID, k: int
    ) -> list[dict]:
        vec_literal = "[" + ",".join(str(v) for v in query_vector) + "]"
        sql = text(
            """
            SELECT id, chunk_text, chunk_index, metadata_json,
                   embedding_vector <=> CAST(:vec AS vector) AS distance
            FROM knowledge_chunks
            WHERE patient_id = :pid
              AND is_active = true
              AND embedding_vector IS NOT NULL
            ORDER BY distance ASC
            LIMIT :k
            """
        )
        result = await self.db.execute(sql, {"vec": vec_literal, "pid": str(patient_id), "k": k})
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

    async def _keyword_search(
        self, query: str, patient_id: uuid.UUID, k: int
    ) -> list[dict]:
        # Split query into keywords and build parameterised ILIKE conditions
        keywords = [w.strip() for w in query.split() if len(w.strip()) >= 3]
        if not keywords:
            return []

        conditions = " OR ".join(f"chunk_text ILIKE :kw{i}" for i in range(len(keywords)))
        params: dict = {"pid": str(patient_id), "k": k}
        for i, kw in enumerate(keywords):
            params[f"kw{i}"] = f"%{kw}%"

        sql = text(
            f"""
            SELECT id, chunk_text, chunk_index, metadata_json
            FROM knowledge_chunks
            WHERE patient_id = :pid
              AND is_active = true
              AND ({conditions})
            ORDER BY created_at DESC
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

    # ------------------------------------------------------------------
    # RRF merge
    # ------------------------------------------------------------------

    @staticmethod
    def _rrf_merge(
        semantic: list[dict], keyword: list[dict], *, top_k: int
    ) -> list[dict]:
        rrf_scores: dict[str, float] = {}
        chunk_data: dict[str, dict] = {}

        for rank, item in enumerate(semantic):
            cid = item["chunk_id"]
            rrf_scores[cid] = rrf_scores.get(cid, 0.0) + 1.0 / (_RRF_K_CONST + rank + 1)
            chunk_data[cid] = item

        for rank, item in enumerate(keyword):
            cid = item["chunk_id"]
            rrf_scores[cid] = rrf_scores.get(cid, 0.0) + 1.0 / (_RRF_K_CONST + rank + 1)
            chunk_data[cid] = item

        ranked = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)[:top_k]
        results = []
        for cid, rrf_score in ranked:
            item = dict(chunk_data[cid])
            item["rrf_score"] = rrf_score
            results.append(item)
        return results

    # ------------------------------------------------------------------
    # Logging
    # ------------------------------------------------------------------

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
            retrieval_type="patient",
            query_text=query_text,
            top_k=top_k,
            result_count=result_count,
            latency_ms=latency_ms,
        )
        self.db.add(record)
        await self.db.flush()
