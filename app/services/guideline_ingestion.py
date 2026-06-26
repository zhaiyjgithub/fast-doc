"""GuidelineIngestionService — Layer 2 source adapter for clinical guideline PDFs.

Orchestrates:
  1. MinerUService: PDF → markdown
  2. ImageEnricher: images → text descriptions via Qwen-VL
  3. MarkdownIngestionService: chunk + embed + persist
"""

from __future__ import annotations

import hashlib
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from pypdf import PdfReader, PdfWriter

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


def _split_pdf(path: Path, *, max_pages: int) -> list[tuple[int, int, bytes]]:
    """Split a PDF into inclusive page ranges with at most ``max_pages`` pages each."""
    reader = PdfReader(str(path))
    total_pages = len(reader.pages)
    if total_pages <= max_pages:
        return []

    parts: list[tuple[int, int, bytes]] = []
    for start in range(0, total_pages, max_pages):
        end = min(start + max_pages, total_pages)
        writer = PdfWriter()
        for index in range(start, end):
            writer.add_page(reader.pages[index])

        with tempfile.SpooledTemporaryFile() as tmp:
            writer.write(tmp)
            tmp.seek(0)
            parts.append((start + 1, end, tmp.read()))
    return parts


@dataclass
class GuidelinePDFSpec:
    """Metadata for a single guideline PDF to ingest."""
    path: Path
    title: str
    version: str | None = None
    markdown_override: Path | None = None  # skip MinerU; use this .md file instead


class GuidelineIngestionService:
    _MAX_MINERU_PAGES = 200

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
        raw_markdown = await self._extract_pdf_markdown(path)
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
        results: list[KnowledgeDocument] = list(skipped_docs)

        # Process MinerU results (store PDF sha256, not markdown sha256)
        for spec in mineru_specs:
            print(f"  Enriching + ingesting: {spec.title} …")
            raw_md = await self._extract_pdf_markdown(spec.path)
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

    async def _extract_pdf_markdown(self, path: Path) -> str:
        """Extract markdown from a PDF, splitting locally if MinerU page limits require it."""
        parts = _split_pdf(path, max_pages=self._MAX_MINERU_PAGES)
        if not parts:
            result = await self._mineru.extract_local_files([path])
            return result[0]

        print(
            f"  Splitting {path.name} into {len(parts)} parts to satisfy MinerU page limits…"
        )
        with tempfile.TemporaryDirectory(prefix="guideline-split-") as temp_dir:
            temp_root = Path(temp_dir)
            temp_paths: list[Path] = []
            for index, (start_page, end_page, pdf_bytes) in enumerate(parts, start=1):
                part_path = temp_root / f"{path.stem}.part{index:02d}_p{start_page}-{end_page}.pdf"
                part_path.write_bytes(pdf_bytes)
                temp_paths.append(part_path)

            markdown_parts = await self._mineru.extract_local_files(temp_paths)
            merged_parts: list[str] = []
            for index, ((start_page, end_page, _), markdown_text) in enumerate(
                zip(parts, markdown_parts),
                start=1,
            ):
                merged_parts.append(
                    f"\n\n<!-- {path.name} part {index}: pages {start_page}-{end_page} -->\n\n"
                    f"{markdown_text.strip()}"
                )
            return "\n".join(merged_parts).strip()
