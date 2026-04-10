"""GuidelineIngestionService — Layer 2 source adapter for clinical guideline PDFs.

Orchestrates:
  1. MinerUService: PDF → markdown
  2. ImageEnricher: images → text descriptions via Qwen-VL
  3. MarkdownIngestionService: chunk + embed + persist
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from app.models.rag import KnowledgeDocument
from app.services.image_enricher import ImageEnricher
from app.services.markdown_ingestion import MarkdownIngestionService
from app.services.mineru_service import MinerUService

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


def _file_sha256(path: Path) -> str:
    """Return the SHA256 hex digest of a file's raw bytes."""
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(65536), b""):
            h.update(block)
    return h.hexdigest()


@dataclass
class GuidelinePDFSpec:
    """Metadata for a single guideline PDF to ingest."""
    path: Path
    title: str
    version: str | None = None
    markdown_override: Path | None = None  # skip MinerU; use this .md file instead


class GuidelineIngestionService:
    def __init__(self, db: "AsyncSession") -> None:
        self.db = db
        self._mineru = MinerUService()
        self._ingestion = MarkdownIngestionService(db)

    async def ingest_pdf_url(
        self,
        url: str,
        *,
        title: str,
        version: str | None = None,
        request_id: str | None = None,
    ) -> KnowledgeDocument:
        """Extract a remote PDF URL, enrich images, and ingest into RAG."""
        raw_markdown = await self._mineru.extract_from_url(url)
        enriched = await ImageEnricher(db=self.db, request_id=request_id).enrich(raw_markdown)
        return await self._ingestion.ingest_markdown(
            markdown_text=enriched,
            title=title,
            source_namespace="guideline",
            source_file=url,
            version=version,
            request_id=request_id,
        )

    async def ingest_pdf_file(
        self,
        path: Path,
        *,
        title: str,
        version: str | None = None,
        request_id: str | None = None,
    ) -> KnowledgeDocument:
        """Extract a single local PDF via MinerU, enrich images, and ingest into RAG."""
        results = await self._mineru.extract_local_files([path])
        raw_markdown = results[0]
        enriched = await ImageEnricher(db=self.db, request_id=request_id).enrich(raw_markdown)
        return await self._ingestion.ingest_markdown(
            markdown_text=enriched,
            title=title,
            source_namespace="guideline",
            source_file=str(path),
            version=version,
            request_id=request_id,
        )

    async def ingest_pdf_files_bulk(
        self,
        specs: list[GuidelinePDFSpec],
        *,
        request_id: str | None = None,
    ) -> list[KnowledgeDocument]:
        """Submit all PDFs in a single MinerU batch, then embed each result.

        Files that have a `markdown_override` skip MinerU entirely and use
        the pre-converted markdown file instead.

        Files whose source PDF hasn't changed (SHA256 match against DB) are
        skipped entirely — no MinerU call, no Qwen embedding.
        """
        from sqlalchemy import select

        # Pre-check: skip specs whose PDF content hasn't changed
        filtered_specs: list[GuidelinePDFSpec] = []
        skipped_docs: list[KnowledgeDocument] = []
        for spec in specs:
            file_sha256 = _file_sha256(spec.path)
            stmt = select(KnowledgeDocument).where(
                KnowledgeDocument.title == spec.title,
                KnowledgeDocument.source_namespace == "guideline",
                KnowledgeDocument.source_sha256 == file_sha256,
            )
            result = await self._ingestion.db.execute(stmt)
            existing = result.scalar_one_or_none()
            if existing:
                print(f"  [skip] '{spec.title}' — PDF unchanged (SHA256 match), skipping MinerU + embedding")
                skipped_docs.append(existing)
            else:
                filtered_specs.append(spec)

        if not filtered_specs:
            return skipped_docs

        # Split remaining specs: those needing MinerU vs those with ready markdown
        mineru_specs = [s for s in filtered_specs if s.markdown_override is None]
        prebuilt_specs = [s for s in filtered_specs if s.markdown_override is not None]

        # Single batch MinerU upload for all PDFs that need conversion
        mineru_markdowns: list[str] = []
        if mineru_specs:
            print(f"  Submitting {len(mineru_specs)} PDF(s) to MinerU in one batch…")
            mineru_markdowns = await self._mineru.extract_local_files(
                [s.path for s in mineru_specs]
            )

        results: list[KnowledgeDocument] = list(skipped_docs)

        # Process MinerU results (store PDF sha256, not markdown sha256)
        for spec, raw_md in zip(mineru_specs, mineru_markdowns):
            print(f"  Enriching + ingesting: {spec.title} …")
            enriched = await ImageEnricher(db=self.db, request_id=request_id).enrich(raw_md)
            doc = await self._ingestion.ingest_markdown(
                markdown_text=enriched,
                title=spec.title,
                source_namespace="guideline",
                source_file=str(spec.path),
                version=spec.version,
                request_id=request_id,
                # Pass the PDF file sha256 so subsequent runs can skip MinerU
                source_sha256_override=_file_sha256(spec.path),
            )
            print(f"    ✓ {spec.title}  → document_id={doc.id}")
            results.append(doc)

        # Process pre-built markdown files (store markdown file sha256)
        for spec in prebuilt_specs:
            print(f"  Ingesting from existing markdown: {spec.title} …")
            raw_md = spec.markdown_override.read_text(encoding="utf-8")  # type: ignore[union-attr]
            enriched = await ImageEnricher(db=self.db, request_id=request_id).enrich(raw_md)
            doc = await self._ingestion.ingest_markdown(
                markdown_text=enriched,
                title=spec.title,
                source_namespace="guideline",
                source_file=str(spec.path),
                version=spec.version,
                request_id=request_id,
                source_sha256_override=_file_sha256(spec.path),
            )
            print(f"    ✓ {spec.title}  → document_id={doc.id}")
            results.append(doc)

        return results

    async def ingest_markdown_file(
        self,
        path: Path,
        *,
        title: str,
        version: str | None = None,
        request_id: str | None = None,
    ) -> KnowledgeDocument:
        """Ingest a pre-converted markdown file directly."""
        markdown_text = path.read_text(encoding="utf-8")
        enriched = await ImageEnricher(db=self.db, request_id=request_id).enrich(markdown_text)
        return await self._ingestion.ingest_markdown(
            markdown_text=enriched,
            title=title,
            source_namespace="guideline",
            source_file=str(path),
            version=version,
            request_id=request_id,
        )
