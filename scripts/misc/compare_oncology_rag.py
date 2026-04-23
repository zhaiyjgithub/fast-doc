#!/usr/bin/env python
"""Oncology RAG quality comparison.

For each of 5 cancer scenarios, generates two EMR SOAP notes:
  - WITHOUT guidelines  (GuidelineRAGService returns empty)
  - WITH guidelines     (full NCCN vector retrieval)

Then prints a side-by-side diff so you can judge whether the
guideline-augmented note is more accurate and actionable.

Usage:
    uv run python -u -m scripts.misc.compare_oncology_rag
"""
from __future__ import annotations

import asyncio
import textwrap
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.models.clinical import Encounter
from app.models.patients import Patient
from app.services.emr_service import EMRService

# ── DB ────────────────────────────────────────────────────────────────────────
engine = create_async_engine(settings.DATABASE_URL, echo=False)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

# ── Oncology test scenarios ───────────────────────────────────────────────────
SCENARIOS: list[dict] = [
    {
        "label": "Invasive Breast Cancer (ER+/HER2-)",
        "transcript": (
            "Doctor: Good morning. Tell me about your recent biopsy results. "
            "Patient: The surgeon called and said the biopsy showed invasive ductal carcinoma, "
            "ER positive, PR positive, HER2 negative. The tumor was 2.1 cm. Two sentinel lymph "
            "nodes were negative. I just had my lumpectomy last week. "
            "Doctor: Have you had your Oncotype DX result yet? "
            "Patient: Yes, my recurrence score came back at 18. "
            "Doctor: Any family history of breast or ovarian cancer? "
            "Patient: My mother had breast cancer at 58. "
            "Doctor: Are you postmenopausal? "
            "Patient: Yes, I am 62 years old. "
            "Doctor: Any bone pain, shortness of breath, or abdominal symptoms? "
            "Patient: No, none of those. I am feeling okay aside from the surgical site."
        ),
    },
    {
        "label": "NSCLC Adenocarcinoma (Stage IIIA, EGFR+)",
        "transcript": (
            "Doctor: Let's review your CT and molecular results. "
            "Patient: The CT scan showed a 3.8 cm mass in the right upper lobe with mediastinal "
            "lymph node involvement at stations 4R and 7. The PET scan confirmed those nodes are "
            "active but no distant metastases. "
            "Doctor: And the molecular testing? "
            "Patient: The pathology came back as adenocarcinoma. The next-generation sequencing "
            "showed an EGFR exon 19 deletion. PD-L1 was 15 percent. "
            "Doctor: Are you a smoker? "
            "Patient: I quit 8 years ago, smoked about 10 pack-years. I am 55 years old. "
            "Doctor: How is your breathing now? "
            "Patient: I get short of breath walking upstairs. My FEV1 was 72 percent predicted. "
            "Doctor: Any weight loss or hemoptysis? "
            "Patient: About 8 pounds over 3 months, no coughing up blood."
        ),
    },
    {
        "label": "Colon Cancer (Stage II, Post-Resection)",
        "transcript": (
            "Doctor: Good afternoon. You had your right hemicolectomy 6 weeks ago. How are you recovering? "
            "Patient: Pretty well, the incision is healed. The pathology showed stage II colon cancer, "
            "T3 N0 M0. The tumor was moderately differentiated. They got clear margins. "
            "Doctor: Did they test for microsatellite instability? "
            "Patient: Yes, the tumor was microsatellite stable, MSS. No mismatch repair deficiency. "
            "Doctor: Any high-risk features on the pathology? "
            "Patient: The report mentioned lymphovascular invasion was present. "
            "Doctor: Any family history of colorectal cancer? "
            "Patient: My brother had colon cancer at 45. I am 58 now. "
            "Doctor: Any rectal bleeding, weight loss, or bowel changes currently? "
            "Patient: No, my bowel movements are normal now. No bleeding."
        ),
    },
    {
        "label": "Prostate Cancer (Intermediate Risk, Gleason 7)",
        "transcript": (
            "Doctor: Let's talk about your prostate biopsy results. "
            "Patient: The urologist said it is prostate cancer, Gleason score 3 plus 4 equals 7, "
            "grade group 2. Six out of 12 cores were positive. The tumor involves about 40 percent "
            "of the biopsy tissue. "
            "Doctor: What was your PSA? "
            "Patient: My PSA was 8.6 before the biopsy. "
            "Doctor: Any urinary symptoms? "
            "Patient: Some hesitancy and nocturia twice a night, but no hematuria. "
            "Doctor: Was the digital rectal exam normal? "
            "Patient: The urologist said the prostate felt enlarged but confined, no extension. "
            "Doctor: Any bone pain or neurological symptoms? "
            "Patient: No bone pain. I am 65 years old and otherwise healthy, no major comorbidities. "
            "Doctor: Did they do any staging imaging? "
            "Patient: MRI pelvis showed the tumor confined to the prostate, stage T2c. No nodal involvement on CT."
        ),
    },
    {
        "label": "Diffuse Large B-Cell Lymphoma (Ann Arbor Stage II)",
        "transcript": (
            "Doctor: Tell me what brought you in. "
            "Patient: I noticed a lump in my neck about two months ago and it has been growing. "
            "I also had one under my right arm. I have been drenching the sheets with night sweats "
            "and I have lost about 15 pounds without trying. I feel exhausted all the time. "
            "Doctor: Did you have a biopsy? "
            "Patient: Yes, the neck node biopsy showed diffuse large B-cell lymphoma, germinal center "
            "B-cell subtype. The immunohistochemistry showed CD20 positive, BCL2 positive, BCL6 positive. "
            "Doctor: What did the staging PET-CT show? "
            "Patient: Two nodal regions on the same side of the diaphragm, the neck and axilla. "
            "No organ involvement. Ann Arbor stage II with B symptoms. "
            "Doctor: Any prior chemotherapy or radiation? "
            "Patient: No, this is my first cancer diagnosis. I am 48 years old. "
            "Doctor: What are your LDH and beta-2 microglobulin? "
            "Patient: LDH was 420, which the doctor said is elevated. Beta-2 microglobulin was 3.1."
        ),
    },
]

# ── Helpers ───────────────────────────────────────────────────────────────────

def _wrap(text: str, width: int = 72) -> str:
    return "\n".join(textwrap.fill(line, width) for line in text.splitlines())


def _print_section(label: str, char: str = "=") -> None:
    print(f"\n{char * 70}")
    print(f"  {label}")
    print(f"{char * 70}")


def _print_soap(soap: dict, prefix: str = "") -> None:
    for section in ("subjective", "objective", "assessment", "plan"):
        content = soap.get(section, "").strip()
        if content:
            print(f"\n  [{section.upper()}]")
            for line in _wrap(content, 68).splitlines():
                print(f"  {line}")


async def _create_temp_patient(db: AsyncSession, suffix: str) -> tuple[uuid.UUID, uuid.UUID]:
    """Insert a throwaway patient + encounter; return (patient_id, encounter_id)."""
    patient_id = uuid.uuid4()
    encounter_id = uuid.uuid4()
    db.add(Patient(
        id=patient_id,
        mrn=f"ONCO-TEST-{suffix}",
        first_name="Test",
        last_name="Oncology",
        primary_language="en-US",
    ))
    db.add(Encounter(
        id=encounter_id,
        patient_id=patient_id,
        encounter_time=datetime.now(timezone.utc),
        care_setting="outpatient",
        chief_complaint="",
        status="draft",
    ))
    await db.flush()
    return patient_id, encounter_id


async def _generate_note(
    db: AsyncSession,
    *,
    patient_id: uuid.UUID,
    encounter_id: uuid.UUID,
    transcript: str,
    use_guidelines: bool,
) -> dict:
    """Run EMRService; optionally suppress guideline retrieval."""
    svc = EMRService(db)

    if use_guidelines:
        state = await svc.generate(
            encounter_id=str(encounter_id),
            patient_id=str(patient_id),
            transcript=transcript,
            request_id=f"rag-cmp-{'on' if use_guidelines else 'off'}-{encounter_id}",
            top_k_guideline=6,
        )
    else:
        with patch(
            "app.services.emr_service.GuidelineRAGService.retrieve",
            new_callable=AsyncMock,
            return_value=[],
        ):
            state = await svc.generate(
                encounter_id=str(encounter_id),
                patient_id=str(patient_id),
                transcript=transcript,
                request_id=f"rag-cmp-off-{encounter_id}",
                top_k_guideline=6,
            )

    return state["soap_note"]


# ── Main ──────────────────────────────────────────────────────────────────────

async def main() -> None:
    print("=" * 70)
    print("  ONCOLOGY RAG QUALITY COMPARISON")
    print("  WITHOUT guidelines  vs  WITH NCCN guidelines")
    print("=" * 70)

    async with SessionLocal() as db:
        for i, scenario in enumerate(SCENARIOS, start=1):
            label = scenario["label"]
            transcript = scenario["transcript"]

            _print_section(f"SCENARIO {i}/5 — {label}")

            # Create two separate encounters for a clean comparison
            pid_off, eid_off = await _create_temp_patient(db, f"{i}A")
            pid_on,  eid_on  = await _create_temp_patient(db, f"{i}B")

            print("\n  Generating WITHOUT guidelines …")
            note_off = await _generate_note(
                db,
                patient_id=pid_off,
                encounter_id=eid_off,
                transcript=transcript,
                use_guidelines=False,
            )

            print("  Generating WITH guidelines …")
            note_on = await _generate_note(
                db,
                patient_id=pid_on,
                encounter_id=eid_on,
                transcript=transcript,
                use_guidelines=True,
            )

            # ── Side-by-side diff ─────────────────────────────────────────
            print("\n" + "─" * 70)
            print("  ▌ WITHOUT NCCN Guidelines")
            print("─" * 70)
            _print_soap(note_off)

            print("\n" + "─" * 70)
            print("  ▌ WITH NCCN Guidelines")
            print("─" * 70)
            _print_soap(note_on)

            # Rollback temp data so the DB stays clean
            await db.rollback()

    await engine.dispose()
    print("\n\n" + "=" * 70)
    print("  COMPARISON COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
