#!/usr/bin/env python
"""Ingest clinical guideline PDFs / markdown files into the RAG system.

Directory layout:
    docs/guidelines/
        respiratory/   GINA asthma + GOLD COPD guidelines
        oncology/      NCCN oncology guidelines (breast, lung, colon, rectal,
                       prostate, lymphoma)

Usage examples:
    # Ingest all guidelines across all specialties
    uv run python -m scripts.ingest_guidelines

    # Ingest a single specialty
    uv run python -m scripts.ingest_guidelines --specialty respiratory
    uv run python -m scripts.ingest_guidelines --specialty oncology

    # Ingest a specific PDF file
    uv run python -m scripts.ingest_guidelines --pdf docs/guidelines/respiratory/GOLD-Report-2025.pdf

    # Ingest pre-converted markdown files from a directory
    uv run python -m scripts.ingest_guidelines --markdown-dir docs/guidelines/respiratory
"""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.services.guideline_ingestion import GuidelineIngestionService, GuidelinePDFSpec

GUIDELINES_DIR = Path(__file__).parent.parent.parent / "docs" / "guidelines"
RESPIRATORY_DIR = GUIDELINES_DIR / "respiratory"
ONCOLOGY_DIR = GUIDELINES_DIR / "oncology"

# Pre-converted markdown files available locally (skip MinerU for these)
_PREBUILT_MD: dict[str, Path] = {}
for _md in RESPIRATORY_DIR.glob("MinerU_markdown_*.md"):
    for _stem in ["GOLD-Pocket-Guide-2025"]:
        if _stem in _md.name:
            _PREBUILT_MD[_stem] = _md

# ── Respiratory (GINA + GOLD) ──────────────────────────────────────────────
RESPIRATORY_SPECS: list[dict] = [
    {
        "file": "GINA-Strategy-Report-2025.pdf",
        "title": "GINA Asthma Strategy Report 2025",
        "version": "2025",
        "specialty": "respiratory",
        "dir": RESPIRATORY_DIR,
    },
    {
        "file": "GINA-Summary-Guide-2025.pdf",
        "title": "GINA Asthma Summary Guide 2025",
        "version": "2025",
        "specialty": "respiratory",
        "dir": RESPIRATORY_DIR,
    },
    {
        "file": "GINA-Severe-Asthma-Guide-2025.pdf",
        "title": "GINA Severe Asthma Guide 2025",
        "version": "2025",
        "specialty": "respiratory",
        "dir": RESPIRATORY_DIR,
    },
    {
        "file": "GOLD-Report-2025.pdf",
        "title": "GOLD COPD Report 2025",
        "version": "2025",
        "specialty": "respiratory",
        "dir": RESPIRATORY_DIR,
    },
    {
        "file": "GOLD-Pocket-Guide-2025.pdf",
        "title": "GOLD COPD Pocket Guide 2025",
        "version": "2025",
        "specialty": "respiratory",
        "dir": RESPIRATORY_DIR,
    },
]

# ── Oncology (NCCN) ────────────────────────────────────────────────────────
ONCOLOGY_SPECS: list[dict] = [
    # Breast
    {
        "file": "NCCN-Breast-Cancer-Invasive-2025.pdf",
        "title": "NCCN Invasive Breast Cancer Guidelines 2025",
        "version": "2025",
        "specialty": "oncology",
        "dir": ONCOLOGY_DIR,
    },
    {
        "file": "NCCN-Breast-Cancer-Metastatic-2025.pdf",
        "title": "NCCN Metastatic Breast Cancer Guidelines 2025",
        "version": "2025",
        "specialty": "oncology",
        "dir": ONCOLOGY_DIR,
    },
    # Lung
    {
        "file": "NCCN-Lung-NSCLC-Early-2026.pdf",
        "title": "NCCN Non-Small Cell Lung Cancer (Early Stage) Guidelines 2026",
        "version": "2026",
        "specialty": "oncology",
        "dir": ONCOLOGY_DIR,
    },
    {
        "file": "NCCN-Lung-NSCLC-Metastatic-2026.pdf",
        "title": "NCCN Non-Small Cell Lung Cancer (Metastatic) Guidelines 2026",
        "version": "2026",
        "specialty": "oncology",
        "dir": ONCOLOGY_DIR,
    },
    {
        "file": "NCCN-Lung-SCLC-2024.pdf",
        "title": "NCCN Small Cell Lung Cancer Guidelines 2024",
        "version": "2024",
        "specialty": "oncology",
        "dir": ONCOLOGY_DIR,
    },
    # Colorectal
    {
        "file": "NCCN-Colon-Cancer-2025.pdf",
        "title": "NCCN Colon Cancer Guidelines 2025",
        "version": "2025",
        "specialty": "oncology",
        "dir": ONCOLOGY_DIR,
    },
    {
        "file": "NCCN-Rectal-Cancer-2025.pdf",
        "title": "NCCN Rectal Cancer Guidelines 2025",
        "version": "2025",
        "specialty": "oncology",
        "dir": ONCOLOGY_DIR,
    },
    # Prostate
    {
        "file": "NCCN-Prostate-Cancer-Early-2026.pdf",
        "title": "NCCN Prostate Cancer (Early Stage) Guidelines 2026",
        "version": "2026",
        "specialty": "oncology",
        "dir": ONCOLOGY_DIR,
    },
    {
        "file": "NCCN-Prostate-Cancer-Advanced-2026.pdf",
        "title": "NCCN Prostate Cancer (Advanced Stage) Guidelines 2026",
        "version": "2026",
        "specialty": "oncology",
        "dir": ONCOLOGY_DIR,
    },
    # Lymphoma
    {
        "file": "NCCN-Lymphoma-DLBCL-2025.pdf",
        "title": "NCCN Diffuse Large B-Cell Lymphoma Guidelines 2025",
        "version": "2025",
        "specialty": "oncology",
        "dir": ONCOLOGY_DIR,
    },
    {
        "file": "NCCN-Lymphoma-Hodgkin-2025.pdf",
        "title": "NCCN Hodgkin Lymphoma Guidelines 2025",
        "version": "2025",
        "specialty": "oncology",
        "dir": ONCOLOGY_DIR,
    },
]

ALL_SPECS: list[dict] = RESPIRATORY_SPECS + ONCOLOGY_SPECS
SPECIALTY_MAP: dict[str, list[dict]] = {
    "respiratory": RESPIRATORY_SPECS,
    "oncology": ONCOLOGY_SPECS,
}

engine = create_async_engine(settings.DATABASE_URL, echo=False)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


def _build_specs(meta_list: list[dict]) -> list[GuidelinePDFSpec]:
    specs = []
    for meta in meta_list:
        base_dir: Path = meta.get("dir", GUIDELINES_DIR)
        path = base_dir / meta["file"]
        if not path.exists():
            print(f"  SKIP (not found): {path}")
            continue
        stem = path.stem
        md_override = _PREBUILT_MD.get(stem)
        if md_override:
            print(f"  Using pre-built markdown for: {meta['title']}")
        specs.append(GuidelinePDFSpec(
            path=path,
            title=meta["title"],
            version=meta.get("version"),
            markdown_override=md_override,
        ))
    return specs


async def ingest_all_pdfs(db: AsyncSession, specialty: str | None = None) -> None:
    """Submit PDFs to MinerU in one batch (most efficient)."""
    meta_list = SPECIALTY_MAP.get(specialty, ALL_SPECS) if specialty else ALL_SPECS
    label = f"{specialty} " if specialty else "all "
    svc = GuidelineIngestionService(db)
    specs = _build_specs(meta_list)
    print(f"\nIngesting {len(specs)} {label}guideline(s) — "
          f"{sum(1 for s in specs if s.markdown_override is None)} via MinerU, "
          f"{sum(1 for s in specs if s.markdown_override is not None)} from pre-built markdown\n")
    docs = await svc.ingest_pdf_files_bulk(specs)
    print(f"\n  Total documents ingested: {len(docs)}")


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
    title = pdf_path.stem.replace("-", " ").replace("_", " ")
    stem = pdf_path.stem
    md_override = _PREBUILT_MD.get(stem)
    spec = GuidelinePDFSpec(path=pdf_path, title=title, version="2025", markdown_override=md_override)
    docs = await svc.ingest_pdf_files_bulk([spec])
    print(f"    → document_id={docs[0].id}")


async def main(args: argparse.Namespace) -> None:
    async with SessionLocal() as db:
        if args.markdown_dir:
            await ingest_markdown_dir(db, Path(args.markdown_dir))
        elif args.pdf:
            await ingest_single_pdf(db, Path(args.pdf))
        else:
            await ingest_all_pdfs(db, specialty=args.specialty)
    await engine.dispose()
    print("\n✅ Guideline ingestion complete.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest clinical guidelines into RAG")
    parser.add_argument("--pdf", help="Path to a single PDF file to ingest")
    parser.add_argument("--markdown-dir", help="Directory of pre-converted .md files to ingest")
    parser.add_argument(
        "--specialty",
        choices=list(SPECIALTY_MAP.keys()),
        help="Ingest only guidelines for a specific specialty (default: all)",
    )
    asyncio.run(main(parser.parse_args()))
