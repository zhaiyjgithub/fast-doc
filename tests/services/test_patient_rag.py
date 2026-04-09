"""Tests for PatientRAGService — RRF merge logic and integration."""

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from app.models.rag import KnowledgeDocument, KnowledgeChunk, RetrievalLog
from app.services.markdown_ingestion import MarkdownIngestionService
from app.services.patient_rag import PatientRAGService


@pytest.fixture
def mock_embed():
    with patch(
        "app.services.markdown_ingestion.llm_adapter.embed",
        new_callable=AsyncMock,
        side_effect=lambda texts, **kw: [[0.1] * 1024 for _ in texts],
    ) as m:
        yield m


@pytest.fixture
def mock_embed_query():
    with patch(
        "app.services.patient_rag.llm_adapter.embed",
        new_callable=AsyncMock,
        return_value=[[0.1] * 1024],
    ) as m:
        yield m


async def test_rrf_merge_deduplicates():
    """Same chunk appearing in both lists should not be duplicated."""
    semantic = [
        {"chunk_id": "a", "chunk_text": "text a", "chunk_index": 0, "metadata_json": None, "score": 0.9},
        {"chunk_id": "b", "chunk_text": "text b", "chunk_index": 1, "metadata_json": None, "score": 0.8},
    ]
    keyword = [
        {"chunk_id": "a", "chunk_text": "text a", "chunk_index": 0, "metadata_json": None, "score": 0.0},
        {"chunk_id": "c", "chunk_text": "text c", "chunk_index": 2, "metadata_json": None, "score": 0.0},
    ]
    merged = PatientRAGService._rrf_merge(semantic, keyword, top_k=5)
    ids = [r["chunk_id"] for r in merged]
    assert len(ids) == len(set(ids))
    # chunk "a" should rank highest (present in both)
    assert ids[0] == "a"


async def test_rrf_merge_respects_top_k():
    semantic = [
        {"chunk_id": str(i), "chunk_text": f"text {i}", "chunk_index": i, "metadata_json": None, "score": 0.0}
        for i in range(10)
    ]
    merged = PatientRAGService._rrf_merge(semantic, [], top_k=3)
    assert len(merged) == 3


async def test_patient_rag_returns_chunks(db_session, mock_embed, mock_embed_query):
    """End-to-end: ingest patient data then retrieve."""
    patient_uuid = uuid.uuid4()

    # Ingest some patient data
    ingest_svc = MarkdownIngestionService(db_session)
    await ingest_svc.ingest_markdown(
        markdown_text=(
            "# Patient Record\n\n"
            "Patient has severe asthma with FEV1 48% predicted.\n"
            "Uses daily Budesonide inhaler 400mcg. " * 30
        ),
        title=f"Patient {patient_uuid} Record",
        source_namespace="patient",
        patient_id=patient_uuid,
    )

    # Retrieve
    rag = PatientRAGService(db_session)
    results = await rag.retrieve(
        query="asthma FEV1 inhaler",
        patient_id=patient_uuid,
        top_k=3,
        request_id="test-retrieve-001",
    )

    assert len(results) >= 1
    assert all("chunk_text" in r for r in results)
    assert all("rrf_score" in r for r in results)


async def test_patient_rag_logs_retrieval(db_session, mock_embed, mock_embed_query):
    patient_uuid = uuid.uuid4()
    ingest_svc = MarkdownIngestionService(db_session)
    await ingest_svc.ingest_markdown(
        markdown_text="COPD with chronic cough " * 50,
        title=f"Patient {patient_uuid} COPD",
        source_namespace="patient",
        patient_id=patient_uuid,
    )

    rag = PatientRAGService(db_session)
    await rag.retrieve(
        query="COPD dyspnea",
        patient_id=patient_uuid,
        top_k=2,
        request_id="test-log-001",
    )

    result = await db_session.execute(
        select(RetrievalLog).where(RetrievalLog.request_id == "test-log-001")
    )
    log = result.scalar_one_or_none()
    assert log is not None
    assert log.retrieval_type == "patient"
