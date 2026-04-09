"""Tests for MinerUService — fully mocked HTTP calls."""

import io
import zipfile
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.services.mineru_service import MinerUError, MinerUService


def _make_zip_with_full_md(content: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("output/full.md", content)
    return buf.getvalue()


@pytest.fixture
def svc():
    return MinerUService(api_key="test-key")


async def test_extract_from_url_success(svc):
    md_content = "# COPD Guideline\n\nContent here."
    zip_bytes = _make_zip_with_full_md(md_content)

    submit_response = MagicMock()
    submit_response.raise_for_status = MagicMock()
    submit_response.json.return_value = {"data": {"task_id": "task-abc"}}

    poll_response = MagicMock()
    poll_response.raise_for_status = MagicMock()
    poll_response.json.return_value = {
        "data": {"state": "done", "full_zip_url": "https://oss.example.com/result.zip"}
    }

    zip_response = MagicMock()
    zip_response.raise_for_status = MagicMock()
    zip_response.content = zip_bytes

    async_client_mock = AsyncMock()
    async_client_mock.__aenter__ = AsyncMock(return_value=async_client_mock)
    async_client_mock.__aexit__ = AsyncMock(return_value=False)
    async_client_mock.post = AsyncMock(return_value=submit_response)
    async_client_mock.get = AsyncMock(side_effect=[poll_response, zip_response])

    with (
        patch("app.services.mineru_service.httpx.AsyncClient", return_value=async_client_mock),
        patch("app.services.mineru_service.asyncio.sleep", new_callable=AsyncMock),
        patch("app.services.mineru_service.asyncio.get_event_loop") as mock_loop,
    ):
        mock_loop.return_value.time.side_effect = [0, 5, 10]
        result = await svc.extract_from_url("https://example.com/guideline.pdf")

    assert result == md_content


async def test_extract_raises_on_failed_state(svc):
    submit_response = MagicMock()
    submit_response.raise_for_status = MagicMock()
    submit_response.json.return_value = {"data": {"task_id": "task-fail"}}

    poll_response = MagicMock()
    poll_response.raise_for_status = MagicMock()
    poll_response.json.return_value = {"data": {"state": "failed", "reason": "parse error"}}

    async_client_mock = AsyncMock()
    async_client_mock.__aenter__ = AsyncMock(return_value=async_client_mock)
    async_client_mock.__aexit__ = AsyncMock(return_value=False)
    async_client_mock.post = AsyncMock(return_value=submit_response)
    async_client_mock.get = AsyncMock(return_value=poll_response)

    with (
        patch("app.services.mineru_service.httpx.AsyncClient", return_value=async_client_mock),
        patch("app.services.mineru_service.asyncio.sleep", new_callable=AsyncMock),
        patch("app.services.mineru_service.asyncio.get_event_loop") as mock_loop,
    ):
        mock_loop.return_value.time.side_effect = [0, 5, 10]
        with pytest.raises(MinerUError, match="failed"):
            await svc.extract_from_url("https://example.com/guideline.pdf")


async def test_download_full_md_missing_raises(svc):
    """ZIP without full.md should raise MinerUError."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("output/figures/fig1.png", b"fake png")
    zip_bytes = buf.getvalue()

    zip_response = MagicMock()
    zip_response.raise_for_status = MagicMock()
    zip_response.content = zip_bytes

    async_client_mock = AsyncMock()
    async_client_mock.__aenter__ = AsyncMock(return_value=async_client_mock)
    async_client_mock.__aexit__ = AsyncMock(return_value=False)
    async_client_mock.get = AsyncMock(return_value=zip_response)

    with patch("app.services.mineru_service.httpx.AsyncClient", return_value=async_client_mock):
        with pytest.raises(MinerUError, match="No full.md"):
            await svc._download_full_md("https://oss.example.com/result.zip")
