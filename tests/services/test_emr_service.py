"""Tests for EMRService — provider-aware prompt construction and SOAP parsing."""

import json
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select

from app.services.emr_service import (
    EMRService,
    build_system_prompt,
    dual_rag_retrieval_query,
    normalize_emr_source_for_storage,
)
from app.services.guideline_rag import GuidelineRAGService
from app.services.patient_rag import PatientRAGService


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


def test_normalize_emr_source_for_storage():
    assert normalize_emr_source_for_storage(None) == "unknown"
    assert normalize_emr_source_for_storage("") == "unknown"
    assert normalize_emr_source_for_storage("  ") == "unknown"
    assert normalize_emr_source_for_storage("paste") == "manual"
    assert normalize_emr_source_for_storage("PASTE") == "manual"
    assert normalize_emr_source_for_storage("voice") == "voice"
    assert normalize_emr_source_for_storage("manual") == "manual"


def test_dual_rag_retrieval_query_optional_provider():
    assert dual_rag_retrieval_query("  visit text  ", None) == "visit text"
    assert dual_rag_retrieval_query("visit", "   ") == "visit"
    merged = dual_rag_retrieval_query("Patient reports cough.", "Post-visit: patient mentioned new rash.")
    assert merged.startswith("Patient reports cough.")
    assert "Post-visit:" in merged
    assert "\n\n" in merged


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
    from datetime import datetime, timezone

    from app.models.clinical import EmrNote, Encounter
    from app.models.patients import Patient
    from app.services.markdown_ingestion import MarkdownIngestionService

    patient_uuid = uuid.uuid4()
    encounter_uuid = uuid.uuid4()

    db_session.add(
        Patient(
            id=patient_uuid,
            mrn="P-EMRTEST1",
            first_name="Test",
            last_name="Patient",
            primary_language="en-US",
        )
    )
    db_session.add(
        Encounter(
            id=encounter_uuid,
            patient_id=patient_uuid,
            encounter_time=datetime.now(timezone.utc),
            care_setting="outpatient",
            chief_complaint="",
            status="draft",
        )
    )
    await db_session.flush()

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

    transcript = "Patient has increased dyspnea for 3 days and productive cough."

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
            side_effect=[soap_response, "Shortness of breath"],
        ),
    ):
        svc = EMRService(db_session)
        state = await svc.generate(
            encounter_id=str(encounter_uuid),
            patient_id=str(patient_uuid),
            transcript=transcript,
            request_id="emr-test-001",
            source="voice",
        )

    assert state["soap_note"]["assessment"] == "COPD exacerbation, moderate"
    assert "ASSESSMENT" in state["emr_text"]
    assert state["encounter_id"] == str(encounter_uuid)
    encounter_after = (
        await db_session.execute(select(Encounter).where(Encounter.id == encounter_uuid))
    ).scalars().first()
    assert encounter_after is not None
    assert encounter_after.transcript_text == transcript
    assert encounter_after.status == "done"
    assert encounter_after.chief_complaint == "Shortness of breath"
    emr_note_after = (
        await db_session.execute(
            select(EmrNote)
            .where(EmrNote.encounter_id == encounter_uuid)
            .order_by(EmrNote.created_at.desc())
            .limit(1)
        )
    ).scalars().first()
    assert emr_note_after is not None
    assert emr_note_after.source == "voice"


async def test_emr_generate_includes_provider_context_in_user_message(db_session):
    """Provider-supplied context is prepended to the LLM user message when set."""
    from datetime import datetime, timezone

    from app.models.clinical import Encounter
    from app.models.patients import Patient

    patient_uuid = uuid.uuid4()
    encounter_uuid = uuid.uuid4()

    db_session.add(
        Patient(
            id=patient_uuid,
            mrn="P-EMRCTX1",
            first_name="Ctx",
            last_name="Test",
            primary_language="en-US",
        )
    )
    db_session.add(
        Encounter(
            id=encounter_uuid,
            patient_id=patient_uuid,
            encounter_time=datetime.now(timezone.utc),
            care_setting="outpatient",
            chief_complaint="",
            status="draft",
        )
    )
    await db_session.flush()

    soap_response = json.dumps({
        "subjective": "S",
        "objective": "O",
        "assessment": "A",
        "plan": "P",
    })
    transcript = "Patient reports cough."
    provider_ctx = "Follow-up visit for hypertension management."

    chat_mock = AsyncMock(return_value=soap_response)

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
            side_effect=[soap_response, "Cough"],
        ) as chat_patch,
    ):
        svc = EMRService(db_session)
        await svc.generate(
            encounter_id=str(encounter_uuid),
            patient_id=str(patient_uuid),
            transcript=transcript,
            provider_context=provider_ctx,
            request_id="emr-ctx-test",
            source="voice",
        )
        chat_patch.assert_awaited()
        first_call = chat_patch.await_args_list[0]
        messages = first_call.kwargs.get("messages") or (
            first_call.args[0] if first_call.args else None
        )
        assert isinstance(messages, list) and len(messages) >= 2
        user_content = messages[1]["content"]
        assert "## Provider-supplied context" in user_content
        assert provider_ctx in user_content
        assert "## Encounter Transcript" in user_content


async def test_emr_generate_rag_retrieve_uses_merged_query(db_session):
    """Patient and guideline RAG receive transcript + provider_context in the embed query."""
    from datetime import datetime, timezone

    from app.models.clinical import Encounter
    from app.models.patients import Patient

    patient_uuid = uuid.uuid4()
    encounter_uuid = uuid.uuid4()

    db_session.add(
        Patient(
            id=patient_uuid,
            mrn="P-EMRRAG1",
            first_name="Rag",
            last_name="Test",
            primary_language="en-US",
        )
    )
    db_session.add(
        Encounter(
            id=encounter_uuid,
            patient_id=patient_uuid,
            encounter_time=datetime.now(timezone.utc),
            care_setting="outpatient",
            chief_complaint="",
            status="draft",
        )
    )
    await db_session.flush()

    soap_response = json.dumps({
        "subjective": "S",
        "objective": "O",
        "assessment": "A",
        "plan": "P",
    })
    transcript = "Patient reports cough."
    provider_ctx = "After visit: patient recalled new penicillin allergy."

    mock_p_retrieve = AsyncMock(return_value=[])
    mock_g_retrieve = AsyncMock(return_value=[])

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
        patch.object(PatientRAGService, "retrieve", mock_p_retrieve),
        patch.object(GuidelineRAGService, "retrieve", mock_g_retrieve),
        patch(
            "app.services.emr_service.llm_adapter.chat",
            new_callable=AsyncMock,
            side_effect=[soap_response, "Cough"],
        ),
    ):
        svc = EMRService(db_session)
        await svc.generate(
            encounter_id=str(encounter_uuid),
            patient_id=str(patient_uuid),
            transcript=transcript,
            provider_context=provider_ctx,
            request_id="emr-rag-merge-test",
            source="voice",
        )

    mock_p_retrieve.assert_awaited()
    pq = mock_p_retrieve.await_args.kwargs.get("query")
    assert pq is not None
    assert transcript in pq
    assert provider_ctx in pq

    mock_g_retrieve.assert_awaited()
    gq = mock_g_retrieve.await_args.kwargs.get("query")
    assert gq is not None
    assert transcript in gq
    assert provider_ctx in gq


async def test_emr_generate_without_provider_context_rag_and_llm_no_extra(
    db_session,
):
    """Contrast: no provider_context → RAG query is transcript-only; LLM has no provider section."""
    from datetime import datetime, timezone

    from app.models.clinical import Encounter
    from app.models.patients import Patient

    patient_uuid = uuid.uuid4()
    encounter_uuid = uuid.uuid4()

    db_session.add(
        Patient(
            id=patient_uuid,
            mrn="P-EMRNOPCTX",
            first_name="No",
            last_name="Ctx",
            primary_language="en-US",
        )
    )
    db_session.add(
        Encounter(
            id=encounter_uuid,
            patient_id=patient_uuid,
            encounter_time=datetime.now(timezone.utc),
            care_setting="outpatient",
            chief_complaint="",
            status="draft",
        )
    )
    await db_session.flush()

    soap_response = json.dumps({
        "subjective": "S",
        "objective": "O",
        "assessment": "A",
        "plan": "P",
    })
    transcript = "  Patient reports cough.  "

    mock_p_retrieve = AsyncMock(return_value=[])
    mock_g_retrieve = AsyncMock(return_value=[])
    chat_patch = AsyncMock(side_effect=[soap_response, "Cough"])

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
        patch.object(PatientRAGService, "retrieve", mock_p_retrieve),
        patch.object(GuidelineRAGService, "retrieve", mock_g_retrieve),
        patch("app.services.emr_service.llm_adapter.chat", chat_patch),
    ):
        svc = EMRService(db_session)
        await svc.generate(
            encounter_id=str(encounter_uuid),
            patient_id=str(patient_uuid),
            transcript=transcript,
            provider_context=None,
            request_id="emr-no-ctx-test",
            source="voice",
        )

    pq = mock_p_retrieve.await_args.kwargs["query"]
    assert pq == transcript.strip()
    assert "## Provider-supplied context" not in pq

    messages = chat_patch.await_args_list[0].kwargs["messages"]
    user_content = messages[1]["content"]
    assert "## Provider-supplied context" not in user_content
    assert "## Encounter Transcript" in user_content


async def test_upsert_chief_complaint_updates_encounter_from_llm_summary():
    encounter = SimpleNamespace(chief_complaint="")
    fake_db = SimpleNamespace(execute=AsyncMock(), flush=AsyncMock())
    svc = EMRService(fake_db)

    with patch(
        "app.services.emr_service.llm_adapter.chat",
        new_callable=AsyncMock,
        return_value='"Shortness of breath"',
    ):
        await svc._upsert_encounter_chief_complaint_from_transcript(
            encounter=encounter,
            transcript="Patient reports shortness of breath for 3 days.",
            request_id="req-cc-001",
        )

    assert encounter.chief_complaint == "Shortness of breath"
    fake_db.flush.assert_awaited_once()


async def test_summarize_chief_complaint_falls_back_to_transcript_when_llm_fails():
    fake_db = SimpleNamespace(execute=AsyncMock(), flush=AsyncMock())
    svc = EMRService(fake_db)

    with patch(
        "app.services.emr_service.llm_adapter.chat",
        new_callable=AsyncMock,
        side_effect=RuntimeError("llm unavailable"),
    ):
        summary = await svc._summarize_chief_complaint_from_transcript(
            transcript="Persistent cough and wheezing with night symptoms.",
            request_id="req-cc-002",
        )

    assert summary == "Persistent cough and wheezing with night symptoms"
