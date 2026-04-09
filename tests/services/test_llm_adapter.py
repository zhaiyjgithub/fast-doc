"""Tests for llm_adapter using pytest-httpx to mock Qwen API responses."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services import llm_adapter


@pytest.fixture(autouse=True)
def reset_client():
    """Reset the module-level client before/after each test."""
    llm_adapter._client = None
    yield
    llm_adapter._client = None


@pytest.fixture
def mock_chat_response():
    response = MagicMock()
    response.choices = [MagicMock()]
    response.choices[0].message.content = "Diagnosis: COPD exacerbation"
    response.usage = MagicMock(prompt_tokens=50, completion_tokens=20)
    return response


@pytest.fixture
def mock_embed_response():
    vector = [0.1] * 1024
    response = MagicMock()
    response.data = [MagicMock(embedding=vector, index=0)]
    response.usage = MagicMock(prompt_tokens=10)
    return response


async def test_chat_returns_content(mock_chat_response):
    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(return_value=mock_chat_response)

    with patch.object(llm_adapter, "get_client", return_value=mock_client):
        result = await llm_adapter.chat([{"role": "user", "content": "diagnose COPD"}])

    assert result == "Diagnosis: COPD exacerbation"


async def test_embed_returns_vectors(mock_embed_response):
    mock_client = MagicMock()
    mock_client.embeddings.create = AsyncMock(return_value=mock_embed_response)

    with patch.object(llm_adapter, "get_client", return_value=mock_client):
        vectors = await llm_adapter.embed(["patient has dyspnea"])

    assert len(vectors) == 1
    assert len(vectors[0]) == 1024


async def test_chat_logs_to_db(mock_chat_response, db_session):
    """Verify that chat() writes a LlmCall record when db is provided."""
    from sqlalchemy import select

    from app.models.ops import LlmCall

    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(return_value=mock_chat_response)

    with patch.object(llm_adapter, "get_client", return_value=mock_client):
        await llm_adapter.chat(
            [{"role": "user", "content": "test"}],
            db=db_session,
            request_id="req-001",
            node_name="test_node",
        )

    result = await db_session.execute(select(LlmCall).where(LlmCall.request_id == "req-001"))
    record = result.scalar_one_or_none()
    assert record is not None
    assert record.call_type == "chat"
    assert record.prompt_tokens == 50
