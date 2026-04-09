"""MarkdownIngestionService — Layer 1 ingestion core.

Accepts pre-formed markdown text and:
  1. Chunks the text (DocumentChunker)
  2. Embeds all chunks in a single batch call
  3. Persists KnowledgeDocument + KnowledgeChunks with deduplication
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import select

from app.models.rag import KnowledgeChunk, KnowledgeDocument
from app.services.chunker import DocumentChunker
from app.services import llm_adapter

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class MarkdownIngestionService:
    def __init__(
        self,
        db: "AsyncSession",
        chunker: DocumentChunker | None = None,
    ) -> None:
        self.db = db
        self.chunker = chunker or DocumentChunker(chunk_size=1000, overlap=200)

    async def ingest_markdown(
        self,
        *,
        markdown_text: str,
        title: str,
        source_namespace: str,  # "patient" | "guideline"
        source_file: str | None = None,
        version: str | None = None,
        patient_id: uuid.UUID | None = None,
        extra_metadata: dict | None = None,
        request_id: str | None = None,
    ) -> KnowledgeDocument:
        """Chunk, embed, and persist a markdown document.

        Returns the persisted :class:`KnowledgeDocument`.
        Duplicate chunks (same ``content_hash``) are silently skipped.
        """
        chunks_raw = self.chunker.split(markdown_text)
        if not chunks_raw:
            raise ValueError("Document produced zero chunks — check the input text")

        # Create or reuse document record
        doc = await self._get_or_create_document(
            title=title,
            source_namespace=source_namespace,
            source_file=source_file,
            version=version,
        )

        # Deduplicate against existing hashes for this document
        existing_hashes = await self._existing_hashes(doc.id)
        new_chunks = [c for c in chunks_raw if c["content_hash"] not in existing_hashes]

        if new_chunks:
            texts = [c["chunk_text"] for c in new_chunks]
            vectors = await llm_adapter.embed(texts, request_id=request_id)

            for chunk_raw, vector in zip(new_chunks, vectors):
                metadata = dict(extra_metadata or {})
                if patient_id:
                    metadata["patient_id"] = str(patient_id)

                chunk = KnowledgeChunk(
                    document_id=doc.id,
                    patient_id=patient_id,
                    chunk_index=chunk_raw["chunk_index"],
                    chunk_text=chunk_raw["chunk_text"],
                    content_hash=chunk_raw["content_hash"],
                    embedding_vector=vector,
                    metadata_json=metadata or None,
                )
                self.db.add(chunk)

        await self.db.commit()
        return doc

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _get_or_create_document(
        self,
        *,
        title: str,
        source_namespace: str,
        source_file: str | None,
        version: str | None,
    ) -> KnowledgeDocument:
        stmt = select(KnowledgeDocument).where(
            KnowledgeDocument.title == title,
            KnowledgeDocument.source_namespace == source_namespace,
        )
        result = await self.db.execute(stmt)
        existing = result.scalar_one_or_none()
        if existing:
            return existing

        doc = KnowledgeDocument(
            source_namespace=source_namespace,
            title=title,
            source_file=source_file,
            version=version,
        )
        self.db.add(doc)
        await self.db.flush()
        return doc

    async def _existing_hashes(self, document_id: uuid.UUID) -> set[str]:
        result = await self.db.execute(
            select(KnowledgeChunk.content_hash).where(KnowledgeChunk.document_id == document_id)
        )
        return {row[0] for row in result.fetchall()}
