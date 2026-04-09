"""Tests for GuidelineRAGService."""

from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from app.models.rag import RetrievalLog
from app.services.guideline_rag import GuidelineRAGService
from app.services.markdown_ingestion import MarkdownIngestionService


@pytest.fixture
def mock_ingest_embed():
    with patch(
        "app.services.markdown_ingestion.llm_adapter.embed",
        new_callable=AsyncMock,
        side_effect=lambda texts, **kw: [[0.2] * 1024 for _ in texts],
    ):
        yield


@pytest.fixture
def mock_query_embed():
    with patch(
        "app.services.guideline_rag.llm_adapter.embed",
        new_callable=AsyncMock,
        return_value=[[0.2] * 1024],
    ):
        yield


async def test_guideline_rag_returns_chunks(db_session, mock_ingest_embed, mock_query_embed):
    """Ingest guideline content then retrieve — must return chunks."""
    svc = MarkdownIngestionService(db_session)
    await svc.ingest_markdown(
        markdown_text=(
            "# GINA Asthma Guidelines\n\n"
            "Step-up therapy: Start with low-dose ICS. "
            "If uncontrolled add LABA. FEV1 >80% target. " * 40
        ),
        title="GINA 2025 Test",
        source_namespace="guideline",
    )

    rag = GuidelineRAGService(db_session)
    results = await rag.retrieve(
        query="asthma ICS LABA FEV1 step therapy",
        top_k=3,
        request_id="gl-test-001",
    )

    assert len(results) >= 1
    for r in results:
        assert "chunk_text" in r
        assert "rrf_score" in r


async def test_guideline_rag_excludes_patient_namespace(db_session, mock_ingest_embed, mock_query_embed):
    """Patient-namespace chunks must NOT appear in guideline results."""
    import uuid

    patient_uuid = uuid.uuid4()
    ingest_svc = MarkdownIngestionService(db_session)

    await ingest_svc.ingest_markdown(
        markdown_text="patient specific data asthma FEV1 " * 50,
        title=f"Patient {patient_uuid} data",
        source_namespace="patient",
        patient_id=patient_uuid,
    )

    rag = GuidelineRAGService(db_session)
    results = await rag.retrieve(query="asthma FEV1", top_k=10)

    # All returned chunks must come from guideline documents
    chunk_ids = [r["chunk_id"] for r in results]
    for result in results:
        assert result.get("metadata_json") is None or "patient_id" not in (
            result.get("metadata_json") or {}
        )


async def test_guideline_rag_logs_retrieval(db_session, mock_ingest_embed, mock_query_embed):
    svc = MarkdownIngestionService(db_session)
    await svc.ingest_markdown(
        markdown_text="COPD exacerbation management with antibiotics and steroids " * 40,
        title="GOLD 2025 COPD Guide Test",
        source_namespace="guideline",
    )

    rag = GuidelineRAGService(db_session)
    await rag.retrieve(query="COPD exacerbation antibiotics", top_k=2, request_id="gl-log-001")

    result = await db_session.execute(
        select(RetrievalLog).where(RetrievalLog.request_id == "gl-log-001")
    )
    log = result.scalar_one_or_none()
    assert log is not None
    assert log.retrieval_type == "guideline"


async def test_guideline_rag_empty_query_returns_gracefully(db_session, mock_query_embed):
    rag = GuidelineRAGService(db_session)
    results = await rag.retrieve(query="it", top_k=5)
    assert isinstance(results, list)
