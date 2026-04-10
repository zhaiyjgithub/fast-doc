"""MarkdownIngestionService — Layer 1 ingestion core.

Accepts pre-formed markdown text and:
  1. Chunks the text (DocumentChunker)
  2. Embeds all chunks in a single batch call
  3. Persists KnowledgeDocument + KnowledgeChunks with deduplication

Deduplication happens at two levels:
  - Document level: SHA256 of the full markdown text — if unchanged, skip entirely.
  - Chunk level:    SHA256 of each chunk — if already stored for this document, skip.
"""

from __future__ import annotations

import hashlib
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import select

from app.models.rag import KnowledgeChunk, KnowledgeDocument
from app.services.chunker import DocumentChunker
from app.services import llm_adapter

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


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
        source_namespace: str,
        source_file: str | None = None,
        version: str | None = None,
        patient_id: uuid.UUID | None = None,
        extra_metadata: dict | None = None,
        request_id: str | None = None,
        source_sha256_override: str | None = None,
    ) -> KnowledgeDocument:
        """Chunk, embed, and persist a markdown document.

        Returns the persisted :class:`KnowledgeDocument`.

        Skip rules:
        - If a document with the same title + source_namespace already exists
          **and** its ``source_sha256`` matches, the document is returned as-is.
        - Individual chunks with a matching ``content_hash`` are silently skipped.

        Args:
            source_sha256_override: When provided, this hash is stored as the
                document's ``source_sha256`` instead of the SHA256 of the markdown
                text.  Use this when the "source" is a binary file (e.g. PDF) whose
                hash is more stable than the MinerU-derived markdown.
        """
        # Use caller-supplied hash (e.g. PDF file bytes) or fall back to markdown hash
        content_sha256 = source_sha256_override or _sha256(markdown_text)
        chunks_raw = self.chunker.split(markdown_text)
        if not chunks_raw:
            raise ValueError("Document produced zero chunks — check the input text")

        # Create or reuse document record; detect unchanged content
        doc, already_indexed = await self._get_or_create_document(
            title=title,
            source_namespace=source_namespace,
            source_file=source_file,
            version=version,
            content_sha256=content_sha256,
        )

        if already_indexed:
            print(f"    [skip] '{title}' unchanged (SHA256 match) — no re-embedding needed")
            return doc

        # Deduplicate at chunk level against existing hashes for this document
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
        content_sha256: str,
    ) -> tuple[KnowledgeDocument, bool]:
        """Return (document, already_indexed).

        ``already_indexed`` is True when an existing document has the same
        ``source_sha256`` — meaning the content hasn't changed and no
        re-embedding is needed.
        """
        stmt = select(KnowledgeDocument).where(
            KnowledgeDocument.title == title,
            KnowledgeDocument.source_namespace == source_namespace,
        )
        result = await self.db.execute(stmt)
        existing = result.scalar_one_or_none()

        if existing:
            if existing.source_sha256 == content_sha256:
                # Content unchanged — safe to skip entirely
                return existing, True
            # Content changed — update sha256 and re-index chunks
            existing.source_sha256 = content_sha256
            if source_file:
                existing.source_file = source_file
            if version:
                existing.version = version
            await self.db.flush()
            return existing, False

        doc = KnowledgeDocument(
            source_namespace=source_namespace,
            title=title,
            source_file=source_file,
            version=version,
            source_sha256=content_sha256,
        )
        self.db.add(doc)
        await self.db.flush()
        return doc, False

    async def _existing_hashes(self, document_id: uuid.UUID) -> set[str]:
        result = await self.db.execute(
            select(KnowledgeChunk.content_hash).where(KnowledgeChunk.document_id == document_id)
        )
        return {row[0] for row in result.fetchall()}
