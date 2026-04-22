"""Tests for CodingService — catalog ingestion and code suggestion."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from app.models.coding import CptCatalog, IcdCatalog
from app.services.catalog_ingestion import CatalogIngestionService
from app.services.coding_service import CodingService


# ------------------------------------------------------------------
# Test fixtures — tiny in-memory CSV/TSV files
# ------------------------------------------------------------------

SAMPLE_ICD_TSV = """\
J45.40\tModerate persistent asthma, uncomplicated
J45.41\tModerate persistent asthma with (acute) exacerbation
J44.1\tChronic obstructive pulmonary disease with (acute) exacerbation
J18.9\tPneumonia, unspecified organism
"""

SAMPLE_CPT_CSV = """\
code,name,description,avg_fee,rvu
99213,Office visit est,Office or other outpatient visit established patient 20-29 min,120.00,1.30
94010,Spirometry,Spirometry measurement of breathing capacity,75.00,0.78
71046,Chest X-ray 2 views,Radiologic examination chest 2 views,85.00,0.96
"""


@pytest.fixture
async def icd_catalog_seeded(db_session, tmp_path):
    tsv = tmp_path / "icd_test.tsv"
    tsv.write_text(SAMPLE_ICD_TSV, encoding="utf-8")
    svc = CatalogIngestionService(db_session)
    count = await svc.ingest_icd(tsv)
    return count


@pytest.fixture
async def cpt_catalog_seeded(db_session, tmp_path):
    csv_f = tmp_path / "cpt_test.csv"
    csv_f.write_text(SAMPLE_CPT_CSV, encoding="utf-8")
    svc = CatalogIngestionService(db_session)
    count = await svc.ingest_cpt(csv_f)
    return count


# ------------------------------------------------------------------
# Catalog ingestion tests
# ------------------------------------------------------------------

async def test_ingest_icd_basic(db_session, icd_catalog_seeded):
    assert icd_catalog_seeded == 4
    result = await db_session.execute(select(IcdCatalog).where(IcdCatalog.code == "J45.40"))
    row = result.scalar_one_or_none()
    assert row is not None
    assert "asthma" in row.description.lower()
    assert row.chapter == "J"


async def test_ingest_icd_dedup(db_session, tmp_path, icd_catalog_seeded):
    tsv = tmp_path / "icd_dup.tsv"
    tsv.write_text(SAMPLE_ICD_TSV, encoding="utf-8")
    svc = CatalogIngestionService(db_session)
    count2 = await svc.ingest_icd(tsv)
    assert count2 == 0  # All already present


async def test_ingest_cpt_basic(db_session, cpt_catalog_seeded):
    assert cpt_catalog_seeded == 3
    result = await db_session.execute(select(CptCatalog).where(CptCatalog.code == "99213"))
    row = result.scalar_one_or_none()
    assert row is not None
    assert row.avg_fee is not None


# ------------------------------------------------------------------
# CodingService — keyword extraction
# ------------------------------------------------------------------

def test_keyword_extraction():
    soap = {
        "assessment": "COPD exacerbation with purulent sputum",
        "plan": "Start prednisone azithromycin, continue tiotropium",
    }
    keywords = CodingService._extract_keywords(soap, "")
    assert any(k in ["copd", "exacerbation", "purulent", "sputum", "prednisone"] for k in keywords)


# ------------------------------------------------------------------
# CodingService — rule engine
# ------------------------------------------------------------------

def test_rule_engine_icd_valid():
    suggestions = [
        {"code": "J44.1", "confidence": 0.9, "rationale": "COPD exacerbation"},
        {"code": "INVALID", "confidence": 0.8, "rationale": "bad code"},
    ]
    valid = CodingService._apply_rule_engine(suggestions, "ICD")
    assert len(valid) == 1
    assert valid[0]["code"] == "J44.1"


def test_rule_engine_cpt_valid():
    suggestions = [
        {"code": "94010", "confidence": 0.85, "rationale": "spirometry"},
        {"code": "ABC", "confidence": 0.5, "rationale": "invalid"},
        {"code": "99213", "confidence": 0.75, "rationale": "office visit"},
    ]
    valid = CodingService._apply_rule_engine(suggestions, "CPT")
    assert len(valid) == 2
    codes = [v["code"] for v in valid]
    assert "94010" in codes
    assert "99213" in codes


def test_dedupe_by_code_keeps_highest_confidence_variant():
    suggestions = [
        {"code": "J18.9", "confidence": 0.80, "status": "suspected", "rationale": "short"},
        {"code": "J18.9", "confidence": 0.95, "status": "present", "rationale": "much longer rationale"},
        {"code": "R50.9", "confidence": 0.70, "status": "present", "rationale": "fever"},
    ]
    deduped = CodingService._dedupe_by_code(suggestions)
    assert len(deduped) == 2
    codes = [item["code"] for item in deduped]
    assert codes.count("J18.9") == 1
    assert "R50.9" in codes
    j189 = next(item for item in deduped if item["code"] == "J18.9")
    assert j189["confidence"] == 0.95


# ------------------------------------------------------------------
# CodingService — end-to-end with mocked LLM
# ------------------------------------------------------------------

async def test_suggest_icd_with_catalog(db_session, icd_catalog_seeded):
    llm_response = json.dumps([
        {"code": "J44.1", "confidence": 0.92, "rationale": "COPD exacerbation with purulent sputum"},
        {"code": "J45.40", "confidence": 0.45, "rationale": "Consider asthma overlap"},
    ])

    with patch(
        "app.services.coding_service.llm_adapter.chat",
        new_callable=AsyncMock,
        return_value=llm_response,
    ):
        svc = CodingService(db_session)
        results = await svc.suggest_icd(
            soap_note={
                "assessment": "COPD exacerbation",
                "plan": "Start prednisone",
                "objective": "",
            },
            emr_text="COPD exacerbation",
            request_id="coding-test-001",
            top_k=3,
        )

    assert len(results) >= 1
    codes = [r["code"] for r in results]
    assert "J44.1" in codes
