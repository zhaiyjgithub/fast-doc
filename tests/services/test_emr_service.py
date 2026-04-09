"""Tests for EMRService — provider-aware prompt construction and SOAP parsing."""

import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.emr_service import EMRService, build_system_prompt


# ---------------------------------------------------------------------------
# Unit tests for prompt construction
# ---------------------------------------------------------------------------

def test_build_system_prompt_pulmonology():
    prompt = build_system_prompt(
        specialty="pulmonology",
        sub_specialty=None,
        credentials="MD",
        prompt_style="standard",
    )
    assert "pulmonologist" in prompt.lower() or "pulmonolog" in prompt.lower()
    assert "standard clinical prose" in prompt


def test_build_system_prompt_critical_care():
    prompt = build_system_prompt(
        specialty="pulmonology",
        sub_specialty="critical_care",
        credentials="MD",
        prompt_style="detailed",
    )
    assert "ventilator" in prompt.lower() or "critical" in prompt.lower()
    assert "thorough and detailed" in prompt


def test_build_system_prompt_bullet_style():
    prompt = build_system_prompt(
        specialty=None,
        sub_specialty=None,
        credentials=None,
        prompt_style="bullet",
    )
    assert "bullet" in prompt.lower()


def test_build_system_prompt_unknown_specialty():
    prompt = build_system_prompt(
        specialty="neurology",
        sub_specialty=None,
        credentials=None,
        prompt_style="standard",
    )
    # Falls back to default prefix
    assert "clinical documentation assistant" in prompt.lower()


# ---------------------------------------------------------------------------
# Unit tests for SOAP parsing
# ---------------------------------------------------------------------------

def test_parse_soap_valid_json():
    raw = json.dumps({
        "subjective": "Patient reports dyspnea",
        "objective": "SpO2 91%, FEV1 48%",
        "assessment": "COPD exacerbation",
        "plan": "Start prednisone 40mg and azithromycin",
    })
    result = EMRService._parse_soap(raw)
    assert result["subjective"] == "Patient reports dyspnea"
    assert result["assessment"] == "COPD exacerbation"


def test_parse_soap_with_markdown_fences():
    raw = '```json\n{"subjective": "Cough x3 weeks", "objective": "Rales", "assessment": "Pneumonia", "plan": "Amoxicillin"}\n```'
    result = EMRService._parse_soap(raw)
    assert result["subjective"] == "Cough x3 weeks"


def test_parse_soap_invalid_json_fallback():
    raw = "Here is the patient note: patient has asthma."
    result = EMRService._parse_soap(raw)
    assert result["subjective"] == raw
    assert result["objective"] == ""


def test_render_emr():
    soap = {
        "subjective": "Dyspnea on exertion",
        "objective": "SpO2 93%",
        "assessment": "COPD Gold III",
        "plan": "Increase Tiotropium",
    }
    emr = EMRService._render_emr(soap)
    assert "SUBJECTIVE" in emr
    assert "OBJECTIVE" in emr
    assert "ASSESSMENT" in emr
    assert "PLAN" in emr


# ---------------------------------------------------------------------------
# Integration test — mocked Qwen
# ---------------------------------------------------------------------------

async def test_emr_generate_with_mocked_llm(db_session):
    """End-to-end EMR generation with all external calls mocked."""
    from app.services.markdown_ingestion import MarkdownIngestionService

    patient_uuid = uuid.uuid4()

    # Seed patient data
    with patch(
        "app.services.markdown_ingestion.llm_adapter.embed",
        new_callable=AsyncMock,
        side_effect=lambda texts, **kw: [[0.3] * 1024 for _ in texts],
    ):
        ingest_svc = MarkdownIngestionService(db_session)
        await ingest_svc.ingest_markdown(
            markdown_text="Patient has COPD GOLD III with FEV1 48%. Uses Tiotropium daily. " * 30,
            title=f"Patient {patient_uuid}",
            source_namespace="patient",
            patient_id=patient_uuid,
        )

    soap_response = json.dumps({
        "subjective": "Increased dyspnea for 3 days, productive cough",
        "objective": "SpO2 91%, FEV1 48% predicted",
        "assessment": "COPD exacerbation, moderate",
        "plan": "Prednisone 40mg x 5 days, Azithromycin 500mg, increase bronchodilator",
    })

    with (
        patch(
            "app.services.patient_rag.llm_adapter.embed",
            new_callable=AsyncMock,
            return_value=[[0.3] * 1024],
        ),
        patch(
            "app.services.guideline_rag.llm_adapter.embed",
            new_callable=AsyncMock,
            return_value=[[0.3] * 1024],
        ),
        patch(
            "app.services.emr_service.llm_adapter.chat",
            new_callable=AsyncMock,
            return_value=soap_response,
        ),
    ):
        svc = EMRService(db_session)
        state = await svc.generate(
            encounter_id="enc-test-001",
            patient_id=str(patient_uuid),
            transcript="Patient has increased dyspnea for 3 days and productive cough.",
            request_id="emr-test-001",
        )

    assert state["soap_note"]["assessment"] == "COPD exacerbation, moderate"
    assert "ASSESSMENT" in state["emr_text"]
    assert state["encounter_id"] == "enc-test-001"
