"""GuidelineIngestionService — Layer 2 source adapter for clinical guideline PDFs.

Orchestrates:
  1. MinerUService: PDF → markdown
  2. ImageEnricher: images → text descriptions via Qwen-VL
  3. MarkdownIngestionService: chunk + embed + persist
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from app.models.rag import KnowledgeDocument
from app.services.image_enricher import ImageEnricher
from app.services.markdown_ingestion import MarkdownIngestionService
from app.services.mineru_service import MinerUService

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


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
        """Extract a local PDF file, enrich images, and ingest into RAG."""
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
