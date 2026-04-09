"""CatalogIngestionService — loads ICD-10-CM and CPT codes into the DB.

ICD source: docs/medical-codes/icd10cm_J_respiratory_2025.tsv (or full TSV)
CPT source: docs/medical-codes/Ref_CPT_202604091710.csv
"""

from __future__ import annotations

import csv
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

from sqlalchemy import select, text

from app.models.coding import CptCatalog, IcdCatalog

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

CATALOG_VERSION_ICD = "ICD10CM-2025"
CATALOG_VERSION_CPT = "CPT-2026"


class CatalogIngestionService:
    def __init__(self, db: "AsyncSession") -> None:
        self.db = db

    # ------------------------------------------------------------------
    # ICD-10-CM
    # ------------------------------------------------------------------

    async def ingest_icd(self, tsv_path: Path) -> int:
        """Load ICD-10-CM codes from a TSV file.

        Expected columns (tab-separated):
          code, description  (min required)
        Chapter is derived from the first letter of the code.
        Returns the count of rows inserted.
        """
        existing = await self._existing_icd_codes()
        count = 0

        with tsv_path.open(newline="", encoding="utf-8") as f:
            reader = csv.reader(f, delimiter="\t")
            for row in reader:
                if len(row) < 2:
                    continue
                code = row[0].strip()
                description = row[1].strip()
                if not code or not description:
                    continue
                if (code, CATALOG_VERSION_ICD) in existing:
                    continue

                chapter = code[0].upper() if code else None
                record = IcdCatalog(
                    code=code,
                    description=description,
                    chapter=chapter,
                    catalog_version=CATALOG_VERSION_ICD,
                )
                self.db.add(record)
                count += 1

                # Batch flush every 500 rows
                if count % 500 == 0:
                    await self.db.flush()

        await self.db.commit()
        return count

    # ------------------------------------------------------------------
    # CPT
    # ------------------------------------------------------------------

    async def ingest_cpt(self, csv_path: Path) -> int:
        """Load CPT codes from the Ref_CPT_202604091710.csv file.

        Expected columns:
          code, name (short_name), description, avg_fee, rvu
        Rows with missing or non-numeric code are skipped.
        Returns the count of rows inserted.
        """
        existing = await self._existing_cpt_codes()
        count = 0

        with csv_path.open(newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                code = (row.get("code") or row.get("CPT Code") or "").strip()
                if not code or not code.isdigit():
                    continue
                if (code, CATALOG_VERSION_CPT) in existing:
                    continue

                short_name = (row.get("name") or row.get("Short Name") or "").strip()[:256]
                description = (row.get("description") or row.get("Description") or "").strip()

                try:
                    avg_fee = float(row.get("avg_fee") or row.get("Avg Fee") or 0)
                except (ValueError, TypeError):
                    avg_fee = None

                try:
                    rvu = float(row.get("rvu") or row.get("RVU") or 0)
                except (ValueError, TypeError):
                    rvu = None

                record = CptCatalog(
                    code=code,
                    short_name=short_name or None,
                    description=description or None,
                    avg_fee=avg_fee,
                    rvu=rvu,
                    catalog_version=CATALOG_VERSION_CPT,
                )
                self.db.add(record)
                count += 1

                if count % 500 == 0:
                    await self.db.flush()

        await self.db.commit()
        return count

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _existing_icd_codes(self) -> set[tuple[str, str]]:
        result = await self.db.execute(
            select(IcdCatalog.code, IcdCatalog.catalog_version).where(
                IcdCatalog.catalog_version == CATALOG_VERSION_ICD
            )
        )
        return {(r.code, r.catalog_version) for r in result.fetchall()}

    async def _existing_cpt_codes(self) -> set[tuple[str, str]]:
        result = await self.db.execute(
            select(CptCatalog.code, CptCatalog.catalog_version).where(
                CptCatalog.catalog_version == CATALOG_VERSION_CPT
            )
        )
        return {(r.code, r.catalog_version) for r in result.fetchall()}
