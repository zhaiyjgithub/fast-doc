"""Tests for MarkdownIngestionService — mocks the embed call."""

from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from app.models.rag import KnowledgeChunk, KnowledgeDocument
from app.services.markdown_ingestion import MarkdownIngestionService


@pytest.fixture
def mock_embed():
    """Patch llm_adapter.embed to return zero vectors."""
    with patch(
        "app.services.markdown_ingestion.llm_adapter.embed",
        new_callable=AsyncMock,
        side_effect=lambda texts, **kw: [[0.0] * 1024 for _ in texts],
    ) as m:
        yield m


async def test_ingest_creates_document(db_session, mock_embed):
    svc = MarkdownIngestionService(db_session)
    doc = await svc.ingest_markdown(
        markdown_text="# Title\n\n" + "clinical text " * 100,
        title="Test Guideline",
        source_namespace="guideline",
    )
    assert doc.id is not None
    assert doc.title == "Test Guideline"
    assert doc.source_namespace == "guideline"


async def test_ingest_creates_chunks(db_session, mock_embed):
    text = "respiratory " * 200  # ~2400 chars → 3 chunks at 1000/200
    svc = MarkdownIngestionService(db_session)
    doc = await svc.ingest_markdown(
        markdown_text=text,
        title="Chunk Test",
        source_namespace="guideline",
    )
    result = await db_session.execute(
        select(KnowledgeChunk).where(KnowledgeChunk.document_id == doc.id)
    )
    chunks = result.scalars().all()
    assert len(chunks) >= 2


async def test_ingest_deduplicates(db_session, mock_embed):
    """Re-ingesting the same document must not create duplicate chunks."""
    text = "dedup test " * 150
    title = "Dedup Doc"
    svc = MarkdownIngestionService(db_session)

    await svc.ingest_markdown(markdown_text=text, title=title, source_namespace="guideline")
    await svc.ingest_markdown(markdown_text=text, title=title, source_namespace="guideline")

    result = await db_session.execute(select(KnowledgeDocument).where(KnowledgeDocument.title == title))
    docs = result.scalars().all()
    assert len(docs) == 1

    result = await db_session.execute(
        select(KnowledgeChunk).where(KnowledgeChunk.document_id == docs[0].id)
    )
    chunks = result.scalars().all()
    hashes = [c.content_hash for c in chunks]
    assert len(hashes) == len(set(hashes))


async def test_ingest_patient_namespace(db_session, mock_embed):
    """Patient namespace chunks should carry patient_id."""
    import uuid

    patient_uuid = uuid.uuid4()
    svc = MarkdownIngestionService(db_session)
    doc = await svc.ingest_markdown(
        markdown_text="patient lab result text " * 100,
        title="Patient P001 Record",
        source_namespace="patient",
        patient_id=patient_uuid,
    )
    result = await db_session.execute(
        select(KnowledgeChunk).where(KnowledgeChunk.document_id == doc.id)
    )
    chunks = result.scalars().all()
    for c in chunks:
        assert c.patient_id == patient_uuid


async def test_ingest_empty_raises(db_session, mock_embed):
    svc = MarkdownIngestionService(db_session)
    with pytest.raises(ValueError, match="zero chunks"):
        await svc.ingest_markdown(
            markdown_text="   ",
            title="Empty",
            source_namespace="guideline",
        )
