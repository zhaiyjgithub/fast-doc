"""Tests for POST /v1/emr/generate endpoint."""

import json
import uuid
from unittest.mock import AsyncMock, patch

import pytest

from app.api.v1.deps import CurrentPrincipal, get_current_user
from app.graph.state import EMRGraphState
from app.main import app


async def _fake_current_user() -> CurrentPrincipal:
    return CurrentPrincipal(id="doctor-1", email="doctor@example.com", user_type="doctor")


@pytest.fixture(autouse=True)
def _override_dependencies():
    app.dependency_overrides[get_current_user] = _fake_current_user
    yield
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def mock_emr_state():
    soap = {
        "subjective": "Patient reports worsening dyspnea",
        "objective": "SpO2 91%, FEV1 48%",
        "assessment": "COPD exacerbation",
        "plan": "Prednisone 40mg, Azithromycin 500mg",
    }
    return EMRGraphState(
        request_id="req-api-001",
        encounter_id="enc-api-001",
        patient_id="00000000-0000-0000-0000-000000000001",
        provider_id="",
        provider_specialty="pulmonology",
        provider_sub_specialty=None,
        provider_credentials="MD",
        provider_prompt_style="standard",
        transcript="Patient has worsening dyspnea",
        patient_chunks=[],
        guideline_chunks=[],
        merged_context="",
        soap_note=soap,
        emr_text="**ASSESSMENT**\nCOPD exacerbation",
        icd_suggestions=[],
        cpt_suggestions=[],
        errors=[],
        current_node="generate_emr",
    )


async def test_emr_generate_success(async_client, mock_emr_state):
    with (
        patch("app.api.v1.endpoints.emr.AuditService.log", new_callable=AsyncMock),
        patch(
            "app.api.v1.endpoints.emr.EMRService.generate",
            new_callable=AsyncMock,
            return_value=mock_emr_state,
        ),
    ):
        response = await async_client.post(
            "/v1/emr/generate",
            json={
                "encounter_id": "enc-api-001",
                "patient_id": "00000000-0000-0000-0000-000000000001",
                "transcript": "Patient has worsening dyspnea for 3 days.",
                "request_id": "req-api-001",
            },
        )

    assert response.status_code == 200
    data = response.json()
    assert data["encounter_id"] == "enc-api-001"
    assert data["soap_note"]["assessment"] == "COPD exacerbation"
    assert "ASSESSMENT" in data["emr_text"]


async def test_emr_generate_missing_required_fields(async_client):
    response = await async_client.post(
        "/v1/emr/generate",
        json={"encounter_id": "enc-001"},  # missing patient_id and transcript
    )
    assert response.status_code == 422


async def test_emr_generate_service_error_returns_500(async_client):
    with (
        patch("app.api.v1.endpoints.emr.AuditService.log", new_callable=AsyncMock),
        patch(
            "app.api.v1.endpoints.emr.EMRService.generate",
            new_callable=AsyncMock,
            side_effect=RuntimeError("Qwen API unreachable"),
        ),
    ):
        response = await async_client.post(
            "/v1/emr/generate",
            json={
                "encounter_id": "enc-err-001",
                "patient_id": "00000000-0000-0000-0000-000000000001",
                "transcript": "Test transcript",
            },
        )

    assert response.status_code == 500
    assert "EMR generation failed" in response.json()["detail"]
