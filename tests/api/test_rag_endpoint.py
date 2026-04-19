"""Tests for POST /v1/rag/markdown endpoints."""

from unittest.mock import AsyncMock, patch

import pytest

from app.api.v1.deps import CurrentPrincipal, require_admin
from app.main import app


async def _fake_admin() -> CurrentPrincipal:
    return CurrentPrincipal(id="admin-1", email="admin@example.com", user_type="admin")


@pytest.fixture(autouse=True)
def _override_dependencies():
    app.dependency_overrides[require_admin] = _fake_admin
    yield
    app.dependency_overrides.pop(require_admin, None)


async def test_ingest_json(async_client):
    with patch(
        "app.services.markdown_ingestion.llm_adapter.embed",
        new_callable=AsyncMock,
        side_effect=lambda texts, **kw: [[0.0] * 1024 for _ in texts],
    ):
        response = await async_client.post(
            "/v1/rag/markdown",
            json={
                "markdown_text": "# Guideline\n\n" + "clinical content " * 100,
                "title": "Test API Guideline",
                "source_namespace": "guideline",
            },
        )

    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "Test API Guideline"
    assert data["source_namespace"] == "guideline"
    assert "document_id" in data


async def test_ingest_empty_returns_422(async_client):
    with patch(
        "app.services.markdown_ingestion.llm_adapter.embed",
        new_callable=AsyncMock,
        side_effect=lambda texts, **kw: [[0.0] * 1024 for _ in texts],
    ):
        response = await async_client.post(
            "/v1/rag/markdown",
            json={
                "markdown_text": "   ",
                "title": "Empty",
                "source_namespace": "guideline",
            },
        )
    assert response.status_code == 422


async def test_ingest_upload(async_client):
    md_content = b"# Upload Test\n\n" + b"respiratory content " * 100
    with patch(
        "app.services.markdown_ingestion.llm_adapter.embed",
        new_callable=AsyncMock,
        side_effect=lambda texts, **kw: [[0.0] * 1024 for _ in texts],
    ):
        response = await async_client.post(
            "/v1/rag/markdown/upload",
            data={"title": "Upload Guideline", "source_namespace": "guideline"},
            files={"file": ("test.md", md_content, "text/markdown")},
        )

    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "Upload Guideline"
