#!/usr/bin/env python
"""Ingest clinical guideline PDFs / markdown files into the RAG system.

Usage examples:
    # Ingest all PDFs from the docs/guidelines directory
    uv run python -m scripts.ingest_guidelines

    # Ingest a specific PDF file
    uv run python -m scripts.ingest_guidelines --pdf docs/guidelines/GOLD-Report-2025.pdf

    # Ingest pre-converted markdown files
    uv run python -m scripts.ingest_guidelines --markdown-dir docs/guidelines
"""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.services.guideline_ingestion import GuidelineIngestionService

GUIDELINES_DIR = Path(__file__).parent.parent / "docs" / "guidelines"

# Default guideline catalogue
GUIDELINE_PDFS = [
    {"file": "GINA-Strategy-Report-2025.pdf", "title": "GINA Asthma Strategy Report 2025", "version": "2025"},
    {"file": "GINA-Summary-Guide-2025.pdf", "title": "GINA Asthma Summary Guide 2025", "version": "2025"},
    {"file": "GINA-Severe-Asthma-Guide-2025.pdf", "title": "GINA Severe Asthma Guide 2025", "version": "2025"},
    {"file": "GOLD-Report-2025.pdf", "title": "GOLD COPD Report 2025", "version": "2025"},
    {"file": "GOLD-Pocket-Guide-2025.pdf", "title": "GOLD COPD Pocket Guide 2025", "version": "2025"},
]

engine = create_async_engine(settings.DATABASE_URL, echo=False)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def ingest_all_pdfs(db: AsyncSession) -> None:
    svc = GuidelineIngestionService(db)
    for meta in GUIDELINE_PDFS:
        path = GUIDELINES_DIR / meta["file"]
        if not path.exists():
            print(f"  SKIP (not found): {path}")
            continue
        print(f"  Ingesting: {meta['title']} …")
        doc = await svc.ingest_pdf_file(path, title=meta["title"], version=meta["version"])
        print(f"    → document_id={doc.id}")


async def ingest_markdown_dir(db: AsyncSession, md_dir: Path) -> None:
    svc = GuidelineIngestionService(db)
    md_files = sorted(md_dir.glob("*.md"))
    if not md_files:
        print(f"  No .md files found in {md_dir}")
        return
    for path in md_files:
        title = path.stem.replace("_", " ").replace("-", " ")
        print(f"  Ingesting markdown: {title} …")
        doc = await svc.ingest_markdown_file(path, title=title, version="unknown")
        print(f"    → document_id={doc.id}")


async def ingest_single_pdf(db: AsyncSession, pdf_path: Path) -> None:
    svc = GuidelineIngestionService(db)
    title = pdf_path.stem.replace("_", " ").replace("-", " ")
    print(f"  Ingesting: {title} …")
    doc = await svc.ingest_pdf_file(pdf_path, title=title)
    print(f"    → document_id={doc.id}")


async def main(args: argparse.Namespace) -> None:
    async with SessionLocal() as db:
        if args.markdown_dir:
            await ingest_markdown_dir(db, Path(args.markdown_dir))
        elif args.pdf:
            await ingest_single_pdf(db, Path(args.pdf))
        else:
            await ingest_all_pdfs(db)
    await engine.dispose()
    print("\n✅ Guideline ingestion complete.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest clinical guidelines into RAG")
    parser.add_argument("--pdf", help="Path to a single PDF file to ingest")
    parser.add_argument("--markdown-dir", help="Directory of pre-converted .md files to ingest")
    asyncio.run(main(parser.parse_args()))
