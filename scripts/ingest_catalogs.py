#!/usr/bin/env python
"""Ingest ICD-10-CM and CPT catalogs into the database.

Usage:
    uv run python -m scripts.ingest_catalogs [--icd] [--cpt] [--all]

Run after alembic upgrade head and before seed_fixtures.
"""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.services.catalog_ingestion import CatalogIngestionService

MEDICAL_CODES_DIR = Path(__file__).parent.parent / "docs" / "medical-codes"

engine = create_async_engine(settings.DATABASE_URL, echo=False)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def ingest_icd(db: AsyncSession) -> None:
    svc = CatalogIngestionService(db)
    tsv = MEDICAL_CODES_DIR / "icd10cm_J_respiratory_2025.tsv"
    if not tsv.exists():
        print(f"  SKIP: {tsv} not found")
        return
    count = await svc.ingest_icd(tsv)
    print(f"  ICD-10-CM J-chapter: {count} rows ingested from {tsv.name}")


async def ingest_cpt(db: AsyncSession) -> None:
    svc = CatalogIngestionService(db)
    csv_file = MEDICAL_CODES_DIR / "Ref_CPT_202604091710.csv"
    if not csv_file.exists():
        print(f"  SKIP: {csv_file} not found")
        return
    count = await svc.ingest_cpt(csv_file)
    print(f"  CPT: {count} rows ingested from {csv_file.name}")


async def main(args: argparse.Namespace) -> None:
    async with SessionLocal() as db:
        if args.all or args.icd:
            print("Ingesting ICD-10-CM catalog…")
            await ingest_icd(db)
        if args.all or args.cpt:
            print("Ingesting CPT catalog…")
            await ingest_cpt(db)
    await engine.dispose()
    print("\n✅ Catalog ingestion complete.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest ICD/CPT catalogs")
    parser.add_argument("--icd", action="store_true", help="Ingest ICD-10-CM J-chapter codes")
    parser.add_argument("--cpt", action="store_true", help="Ingest CPT codes")
    parser.add_argument("--all", action="store_true", default=True, help="Ingest all catalogs (default)")
    asyncio.run(main(parser.parse_args()))
