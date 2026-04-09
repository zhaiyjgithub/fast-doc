#!/usr/bin/env python
"""Seed fixture data into the database.

Usage:
    uv run python -m scripts.seed_fixtures

Loads CSV fixtures and ingests patient RAG chunks directly via
MarkdownIngestionService (no HTTP call needed).
"""

from __future__ import annotations

import asyncio
import csv
import sys
import uuid
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.models.clinical import (
    AllergyRecord,
    DiagnosisRecord,
    Encounter,
    LabReport,
    LabResult,
    MedicationRecord,
)
from app.models.patients import Patient, PatientDemographics
from app.models.providers import Provider
from app.services.markdown_ingestion import MarkdownIngestionService

FIXTURES_DIR = Path(__file__).parent.parent / "docs" / "fixtures"

engine = create_async_engine(settings.DATABASE_URL, echo=False)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

# Map external IDs → DB UUIDs populated during seeding
_patient_map: dict[str, uuid.UUID] = {}
_provider_map: dict[str, uuid.UUID] = {}
_lab_report_map: dict[str, uuid.UUID] = {}


def _csv(name: str) -> list[dict]:
    path = FIXTURES_DIR / name
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


async def seed_patients(db: AsyncSession) -> None:
    print("Seeding patients…")
    for row in _csv("patients.csv"):
        p = Patient(
            mrn=row["external_patient_id"],
            first_name=row["name_masked"][0],
            last_name=row["name_masked"].split()[-1] if " " in row["name_masked"] else "Unknown",
            date_of_birth=row["date_of_birth"] or None,
            gender=row.get("sex_at_birth"),
            primary_language=row.get("primary_language", "en-US"),
        )
        db.add(p)
        await db.flush()
        _patient_map[row["patient_id"]] = p.id

        demographics = PatientDemographics(
            patient_id=p.id,
            allergy_summary_json=row.get("allergy_summary_json") or None,
        )
        db.add(demographics)
    await db.commit()
    print(f"  {len(_patient_map)} patients seeded")


async def seed_providers(db: AsyncSession) -> None:
    print("Seeding providers…")
    for row in _csv("providers.csv"):
        prov = Provider(
            external_provider_id=row["external_provider_id"],
            first_name=row["first_name"],
            last_name=row["last_name"],
            full_name=row["full_name"],
            gender=row.get("gender") or None,
            date_of_birth=row.get("date_of_birth") or None,
            credentials=row.get("credentials") or None,
            specialty=row.get("specialty") or None,
            sub_specialty=row.get("sub_specialty") or None,
            department=row.get("department") or None,
            license_number=row.get("license_number") or None,
            license_state=row.get("license_state") or None,
            prompt_style=row.get("prompt_style", "standard"),
            is_active=row.get("is_active", "true").lower() == "true",
        )
        db.add(prov)
        await db.flush()
        _provider_map[row["provider_id"]] = prov.id
    await db.commit()
    print(f"  {len(_provider_map)} providers seeded")


async def seed_encounters(db: AsyncSession) -> None:
    print("Seeding encounters…")
    count = 0
    for row in _csv("encounters.csv"):
        patient_id = _patient_map.get(row["patient_id"])
        provider_id = _provider_map.get(row.get("provider_id", ""))
        if not patient_id:
            print(f"  WARN: unknown patient_id={row['patient_id']}")
            continue
        enc = Encounter(
            patient_id=patient_id,
            provider_id=provider_id,
            encounter_time=row["encounter_time"],
            care_setting=row.get("care_setting", "outpatient"),
            department=row.get("department") or None,
            chief_complaint=row.get("chief_complaint") or None,
            transcript_text=row.get("transcript_text") or None,
            status=row.get("status", "completed"),
        )
        db.add(enc)
        count += 1
    await db.commit()
    print(f"  {count} encounters seeded")


async def seed_lab_reports_and_results(db: AsyncSession) -> None:
    print("Seeding lab reports and results…")
    from sqlalchemy import select

    lr_rows = _csv("lab_reports.csv")
    for row in lr_rows:
        patient_id = _patient_map.get(row["patient_id"])
        if not patient_id:
            continue
        lr = LabReport(
            patient_id=patient_id,
            report_type=row.get("report_type") or None,
            report_time=row.get("report_time") or None,
            summary_text=row.get("summary_text") or None,
        )
        db.add(lr)
        await db.flush()
        _lab_report_map[row["lab_report_id"]] = lr.id

    result_rows = _csv("lab_results.csv")
    for row in result_rows:
        report_id = _lab_report_map.get(row["lab_report_id"])
        if not report_id:
            continue
        r = LabResult(
            report_id=report_id,
            test_name=row["test_name"],
            value=row.get("value_text") or None,
            unit=row.get("unit") or None,
            reference_range=row.get("reference_range") or None,
            abnormal_flag=row.get("abnormal_flag") or None,
        )
        db.add(r)
    await db.commit()
    print(f"  {len(_lab_report_map)} lab reports seeded")


async def seed_medications(db: AsyncSession) -> None:
    print("Seeding medications…")
    count = 0
    for row in _csv("medication_records.csv"):
        patient_id = _patient_map.get(row.get("patient_id", ""))
        if not patient_id:
            continue
        med = MedicationRecord(
            patient_id=patient_id,
            drug_name=row["drug_name"],
            dosage=row.get("dosage") or None,
            frequency=row.get("frequency") or None,
            route=row.get("route") or None,
            is_active=row.get("is_active", "true").lower() == "true",
        )
        db.add(med)
        count += 1
    await db.commit()
    print(f"  {count} medication records seeded")


async def seed_diagnoses(db: AsyncSession) -> None:
    print("Seeding diagnoses…")
    count = 0
    for row in _csv("diagnosis_records.csv"):
        patient_id = _patient_map.get(row.get("patient_id", ""))
        if not patient_id:
            continue
        diag = DiagnosisRecord(
            patient_id=patient_id,
            icd_code=row.get("icd_code") or None,
            description=row.get("description") or None,
            is_primary=row.get("is_primary", "false").lower() == "true",
        )
        db.add(diag)
        count += 1
    await db.commit()
    print(f"  {count} diagnosis records seeded")


async def seed_patient_rag(db: AsyncSession) -> None:
    """Build per-patient RAG documents from encounters and lab results."""
    print("Ingesting patient RAG chunks…")
    from sqlalchemy import select

    svc = MarkdownIngestionService(db)
    total_docs = 0

    for ext_id, patient_uuid in _patient_map.items():
        # Gather encounter transcripts
        result = await db.execute(
            select(Encounter).where(Encounter.patient_id == patient_uuid)
        )
        encounters = result.scalars().all()

        # Gather lab results
        result = await db.execute(
            select(LabReport).where(LabReport.patient_id == patient_uuid)
        )
        lab_reports = result.scalars().all()

        report_ids = [lr.id for lr in lab_reports]
        lab_results: list[LabResult] = []
        for rep_id in report_ids:
            res = await db.execute(select(LabResult).where(LabResult.report_id == rep_id))
            lab_results.extend(res.scalars().all())

        if not encounters and not lab_results:
            continue

        # Build markdown
        lines = [f"# Patient {ext_id} Clinical Record\n"]
        for enc in encounters:
            lines.append(f"## Encounter {enc.encounter_time}")
            if enc.chief_complaint:
                lines.append(f"**Chief Complaint:** {enc.chief_complaint}")
            if enc.transcript_text:
                lines.append(enc.transcript_text)
            lines.append("")

        if lab_results:
            lines.append("## Lab Results")
            for lr in lab_results:
                flag = f" [{lr.abnormal_flag}]" if lr.abnormal_flag else ""
                lines.append(
                    f"- {lr.test_name}: {lr.value} {lr.unit or ''} "
                    f"(ref: {lr.reference_range or 'N/A'}){flag}"
                )

        abnormal_flags = {lr.test_name: lr.abnormal_flag for lr in lab_results if lr.abnormal_flag}

        markdown_text = "\n".join(lines)
        await svc.ingest_markdown(
            markdown_text=markdown_text,
            title=f"Patient {ext_id} Clinical Record",
            source_namespace="patient",
            patient_id=patient_uuid,
            extra_metadata={"abnormal_flags": abnormal_flags},
        )
        total_docs += 1
        print(f"  Patient {ext_id}: RAG document ingested")

    print(f"  {total_docs} patient RAG documents ingested")


async def main() -> None:
    async with SessionLocal() as db:
        await seed_patients(db)
        await seed_providers(db)
        await seed_encounters(db)
        await seed_lab_reports_and_results(db)
        await seed_medications(db)
        await seed_diagnoses(db)
        await seed_patient_rag(db)
    await engine.dispose()
    print("\n✅ Fixture seeding complete.")


if __name__ == "__main__":
    asyncio.run(main())
