#!/usr/bin/env python
"""Seed fixture data into the database.

Usage:
    uv run python -m scripts.seed_fixtures          # seed everything
    uv run python -m scripts.seed_fixtures --no-rag # skip RAG embedding (no Qwen needed)
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import uuid
from datetime import date, datetime, timezone
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

FIXTURES_DIR = Path(__file__).parent.parent / "docs" / "fixtures"


def _parse_date(val: str | None) -> date | None:
    """Parse ISO date string to date object; returns None for empty/invalid."""
    if not val:
        return None
    try:
        return datetime.fromisoformat(val.replace("Z", "+00:00")).date()
    except (ValueError, AttributeError):
        return None


def _parse_dt(val: str | None) -> datetime | None:
    """Parse ISO datetime string to timezone-aware datetime; returns None if empty."""
    if not val:
        return None
    try:
        dt = datetime.fromisoformat(val.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, AttributeError):
        return None

engine = create_async_engine(settings.DATABASE_URL, echo=False)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

# external-id → DB UUID maps (populated as seeding runs)
_patient_map: dict[str, uuid.UUID] = {}   # e.g. "p001" → UUID
_provider_map: dict[str, uuid.UUID] = {}  # e.g. "d001" → UUID
_encounter_map: dict[str, uuid.UUID] = {} # e.g. "e001" → UUID
_lab_report_map: dict[str, uuid.UUID] = {}


def _csv(name: str) -> list[dict]:
    path = FIXTURES_DIR / name
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


# ---------------------------------------------------------------------------
# Patients  (basic info from patients.csv, rich PII from patient_demographics.csv)
# ---------------------------------------------------------------------------

async def seed_patients(db: AsyncSession) -> None:
    print("Seeding patients…")
    from sqlalchemy import select

    # Build demographics lookup keyed by patient external id
    demo_lookup = {row["patient_id"]: row for row in _csv("patient_demographics.csv")}

    for row in _csv("patients.csv"):
        # Skip if already seeded (idempotent)
        existing = await db.execute(
            select(Patient.id).where(Patient.mrn == row["external_patient_id"])
        )
        if ex := existing.scalar_one_or_none():
            _patient_map[row["patient_id"]] = ex
            continue

        demo = demo_lookup.get(row["patient_id"], {})
        first_name = demo.get("first_name") or row.get("name_masked", "Unknown").split()[0]
        last_name = demo.get("last_name") or (row.get("name_masked", "Unknown").split()[-1]
                                               if " " in row.get("name_masked", "") else "Unknown")

        p = Patient(
            mrn=row["external_patient_id"],
            first_name=first_name,
            last_name=last_name,
            date_of_birth=_parse_date(demo.get("date_of_birth") or row.get("date_of_birth")),
            gender=demo.get("gender") or row.get("sex_at_birth") or None,
            primary_language=demo.get("preferred_language") or row.get("primary_language", "en-US"),
        )
        db.add(p)
        await db.flush()
        _patient_map[row["patient_id"]] = p.id

        # Encrypt phone before storing (security module; falls back to raw if key not set)
        from app.core.security import encrypt
        raw_phone = demo.get("mobile_phone") or demo.get("home_phone") or None
        phone_stored = encrypt(raw_phone) if raw_phone else None

        demographics = PatientDemographics(
            patient_id=p.id,
            ssn_last4=demo.get("ssn_last4") or None,
            phone=phone_stored,
            email=demo.get("email") or None,
            address_line1=(
                (demo.get("street_address") or "") +
                (" " + demo.get("apt", "") if demo.get("apt") else "")
            ).strip() or None,
            city=demo.get("city") or None,
            state=demo.get("state") or None,
            zip_code=demo.get("zip_code") or None,
            allergy_summary_json=row.get("allergy_summary_json") or None,
        )
        db.add(demographics)

    await db.commit()
    print(f"  {len(_patient_map)} patients seeded")


# ---------------------------------------------------------------------------
# Providers
# ---------------------------------------------------------------------------

async def seed_providers(db: AsyncSession) -> None:
    print("Seeding providers…")
    from sqlalchemy import select

    for row in _csv("providers.csv"):
        existing = await db.execute(
            select(Provider.id).where(Provider.external_provider_id == row["external_provider_id"])
        )
        if ex := existing.scalar_one_or_none():
            _provider_map[row["provider_id"]] = ex
            continue

        prov = Provider(
            external_provider_id=row["external_provider_id"],
            first_name=row["first_name"],
            last_name=row["last_name"],
            full_name=row["full_name"],
            gender=row.get("gender") or None,
            date_of_birth=_parse_date(row.get("date_of_birth")),
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


# ---------------------------------------------------------------------------
# Encounters
# ---------------------------------------------------------------------------

async def seed_encounters(db: AsyncSession) -> None:
    print("Seeding encounters…")
    from sqlalchemy import select

    count = 0
    skipped = 0
    for row in _csv("encounters.csv"):
        patient_id = _patient_map.get(row["patient_id"])
        provider_id = _provider_map.get(row.get("provider_id", ""))
        if not patient_id:
            print(f"  WARN: unknown patient_id={row['patient_id']}")
            continue

        # Skip if encounter already exists (match by patient + time)
        existing = await db.execute(
            select(Encounter.id).where(
                Encounter.patient_id == patient_id,
                Encounter.encounter_time == _parse_dt(row["encounter_time"]),
            )
        )
        if ex := existing.scalar_one_or_none():
            _encounter_map[row["encounter_id"]] = ex
            skipped += 1
            continue

        enc = Encounter(
            patient_id=patient_id,
            provider_id=provider_id,
            encounter_time=_parse_dt(row["encounter_time"]),
            care_setting=row.get("care_setting", "outpatient"),
            department=row.get("department") or None,
            chief_complaint=row.get("chief_complaint") or None,
            transcript_text=row.get("transcript_text") or None,
            status=row.get("status", "completed"),
        )
        db.add(enc)
        await db.flush()
        _encounter_map[row["encounter_id"]] = enc.id
        count += 1

    await db.commit()
    print(f"  {count} encounters seeded ({skipped} skipped, already existed)")


# ---------------------------------------------------------------------------
# Lab reports + results
# CSV columns: lab_report_id, patient_id, encounter_id, report_time,
#              report_source, report_text_raw, file_uri
# ---------------------------------------------------------------------------

async def seed_lab_reports_and_results(db: AsyncSession) -> None:
    print("Seeding lab reports and results…")

    for row in _csv("lab_reports.csv"):
        patient_id = _patient_map.get(row["patient_id"])
        if not patient_id:
            continue
        encounter_id = _encounter_map.get(row.get("encounter_id", ""))

        lr = LabReport(
            patient_id=patient_id,
            encounter_id=encounter_id,
            report_type=row.get("report_source") or None,
            report_time=_parse_dt(row.get("report_time")),
            # CSV uses report_text_raw; model field is summary_text
            summary_text=row.get("report_text_raw") or row.get("summary_text") or None,
        )
        db.add(lr)
        await db.flush()
        _lab_report_map[row["lab_report_id"]] = lr.id

    for row in _csv("lab_results.csv"):
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
    print(f"  {len(_lab_report_map)} lab reports + results seeded")


# ---------------------------------------------------------------------------
# Medications
# CSV columns: medication_id, patient_id, encounter_id, medication_name,
#              dose, route, frequency, start_date, end_date, indication, is_active
# ---------------------------------------------------------------------------

async def seed_medications(db: AsyncSession) -> None:
    print("Seeding medications…")
    count = 0
    for row in _csv("medication_records.csv"):
        patient_id = _patient_map.get(row.get("patient_id", ""))
        if not patient_id:
            continue
        encounter_id = _encounter_map.get(row.get("encounter_id", ""))

        med = MedicationRecord(
            patient_id=patient_id,
            encounter_id=encounter_id,
            # CSV uses medication_name; model field is drug_name
            drug_name=row.get("medication_name") or row.get("drug_name") or "Unknown",
            dosage=row.get("dose") or row.get("dosage") or None,
            frequency=row.get("frequency") or None,
            route=row.get("route") or None,
            start_date=_parse_dt(row.get("start_date")),
            end_date=_parse_dt(row.get("end_date")),
            is_active=row.get("is_active", "true").lower() == "true",
        )
        db.add(med)
        count += 1

    await db.commit()
    print(f"  {count} medication records seeded")


# ---------------------------------------------------------------------------
# Diagnoses
# CSV columns: diagnosis_id, encounter_id, diagnosis_text, is_primary,
#              clinical_status, onset_date
# ---------------------------------------------------------------------------

async def seed_diagnoses(db: AsyncSession) -> None:
    print("Seeding diagnoses…")
    import re

    # Build a reverse map: encounter external id → patient external id
    enc_to_patient = {row["encounter_id"]: row["patient_id"] for row in _csv("encounters.csv")}

    count = 0
    for row in _csv("diagnosis_records.csv"):
        ext_enc_id = row.get("encounter_id", "")
        encounter_id = _encounter_map.get(ext_enc_id)
        if not encounter_id:
            continue

        patient_id = _patient_map.get(enc_to_patient.get(ext_enc_id, ""))
        if not patient_id:
            continue

        text = row.get("diagnosis_text") or row.get("description") or ""
        icd_match = re.search(r"\(([A-Z]\d{2}[\.\w]*)\)", text)
        icd_code = icd_match.group(1) if icd_match else None

        diag = DiagnosisRecord(
            patient_id=patient_id,
            encounter_id=encounter_id,
            icd_code=icd_code,
            description=text,
            is_primary=row.get("is_primary", "false").lower() == "true",
        )
        db.add(diag)
        count += 1

    await db.commit()
    print(f"  {count} diagnosis records seeded")


# ---------------------------------------------------------------------------
# Allergy records
# CSV columns: allergy_id, patient_id, allergen, reaction, severity,
#              status, recorded_at
# ---------------------------------------------------------------------------

async def seed_allergies(db: AsyncSession) -> None:
    print("Seeding allergy records…")
    count = 0
    for row in _csv("allergy_records.csv"):
        patient_id = _patient_map.get(row.get("patient_id", ""))
        if not patient_id:
            continue

        allergy = AllergyRecord(
            patient_id=patient_id,
            allergen=row["allergen"],
            reaction=row.get("reaction") or None,
            severity=row.get("severity") or None,
            # CSV uses recorded_at; model field is onset_date
            onset_date=_parse_dt(row.get("recorded_at") or row.get("onset_date")),
            is_active=row.get("status", "active").lower() == "active",
        )
        db.add(allergy)
        count += 1

    await db.commit()
    print(f"  {count} allergy records seeded")


# ---------------------------------------------------------------------------
# Patient RAG — builds markdown from encounters+labs, embeds via Qwen
# ---------------------------------------------------------------------------

async def seed_patient_rag(db: AsyncSession) -> None:
    print("Ingesting patient RAG chunks (calls Qwen embedding API)…")
    from sqlalchemy import select

    from app.models.clinical import Encounter, LabReport, LabResult
    from app.services.markdown_ingestion import MarkdownIngestionService

    svc = MarkdownIngestionService(db)
    total_docs = 0

    for ext_id, patient_uuid in _patient_map.items():
        result = await db.execute(
            select(Encounter).where(Encounter.patient_id == patient_uuid)
        )
        encounters = result.scalars().all()

        result = await db.execute(
            select(LabReport).where(LabReport.patient_id == patient_uuid)
        )
        lab_reports = result.scalars().all()

        lab_results: list[LabResult] = []
        for rep in lab_reports:
            res = await db.execute(select(LabResult).where(LabResult.report_id == rep.id))
            lab_results.extend(res.scalars().all())

        if not encounters and not lab_results:
            print(f"  SKIP {ext_id}: no data to embed")
            continue

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


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def _load_existing_maps(db: AsyncSession) -> None:
    """Populate _patient_map / _provider_map / _encounter_map from the DB.

    Used by --rag-only mode so the RAG step can find existing records.
    """
    from sqlalchemy import select

    for row in _csv("patients.csv"):
        r = await db.execute(select(Patient.id).where(Patient.mrn == row["external_patient_id"]))
        if pk := r.scalar_one_or_none():
            _patient_map[row["patient_id"]] = pk

    for row in _csv("providers.csv"):
        r = await db.execute(
            select(Provider.id).where(Provider.external_provider_id == row["external_provider_id"])
        )
        if pk := r.scalar_one_or_none():
            _provider_map[row["provider_id"]] = pk

    for row in _csv("encounters.csv"):
        patient_id = _patient_map.get(row["patient_id"])
        if not patient_id:
            continue
        r = await db.execute(
            select(Encounter.id).where(
                Encounter.patient_id == patient_id,
                Encounter.encounter_time == _parse_dt(row["encounter_time"]),
            )
        )
        if pk := r.scalar_one_or_none():
            _encounter_map[row["encounter_id"]] = pk

    print(f"  Loaded {len(_patient_map)} patients, {len(_encounter_map)} encounters from DB")


async def main(skip_rag: bool = False, rag_only: bool = False) -> None:
    async with SessionLocal() as db:
        if rag_only:
            print("RAG-only mode: loading existing records from DB…")
            await _load_existing_maps(db)
            await seed_patient_rag(db)
        else:
            await seed_patients(db)
            await seed_providers(db)
            await seed_encounters(db)
            await seed_lab_reports_and_results(db)
            await seed_medications(db)
            await seed_diagnoses(db)
            await seed_allergies(db)
            if not skip_rag:
                await seed_patient_rag(db)
            else:
                print("Skipping patient RAG ingestion (--no-rag)")
    await engine.dispose()
    print("\n✅ Fixture seeding complete.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-rag", action="store_true", help="Skip patient RAG embedding step")
    parser.add_argument("--rag-only", action="store_true", help="Only run patient RAG ingestion (data must already be seeded)")
    args = parser.parse_args()
    asyncio.run(main(skip_rag=args.no_rag, rag_only=args.rag_only))
