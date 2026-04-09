"""Tests for ImageEnricher."""

from unittest.mock import AsyncMock, patch

import pytest

from app.services.image_enricher import ImageEnricher


async def test_no_images_unchanged():
    enricher = ImageEnricher()
    text = "# COPD Management\n\nPatients should use bronchodilators."
    result = await enricher.enrich(text)
    assert result == text


async def test_clinical_image_replaced():
    md = "## FEV1 Chart\n\n![FEV1 trend](https://cdn.mineru.net/img/chart.png)\n\nSee above."
    with patch(
        "app.services.image_enricher.llm_adapter.describe_image",
        new_callable=AsyncMock,
        return_value="Line chart showing FEV1 declining over 3 years from 75% to 48% predicted.",
    ):
        enricher = ImageEnricher()
        result = await enricher.enrich(md)

    assert "![FEV1 trend]" not in result
    assert "[IMAGE:" in result
    assert "FEV1 declining" in result


async def test_decorative_image_removed():
    md = "![logo](https://example.com/logo.png)\n\n# Main Content"
    enricher = ImageEnricher()
    result = await enricher.enrich(md)

    assert "![logo]" not in result
    assert "[IMAGE:" not in result
    assert "# Main Content" in result


async def test_multiple_images_processed():
    md = (
        "![spirometry](https://cdn.example.com/spirometry.png)\n\n"
        "Some text\n\n"
        "![chest-xray](https://cdn.example.com/cxr.png)\n\n"
        "More text"
    )
    call_count = 0

    async def fake_describe(url, **kwargs):
        nonlocal call_count
        call_count += 1
        return f"Description of image at {url}"

    with patch("app.services.image_enricher.llm_adapter.describe_image", side_effect=fake_describe):
        enricher = ImageEnricher()
        result = await enricher.enrich(md)

    assert call_count == 2
    assert "![spirometry]" not in result
    assert "![chest-xray]" not in result
    assert result.count("[IMAGE:") == 2


async def test_image_description_disabled(monkeypatch):
    monkeypatch.setattr("app.services.image_enricher.settings.IMAGE_DESCRIPTION_ENABLED", False)
    md = "![chart](https://cdn.example.com/chart.png)\n\nContent"
    enricher = ImageEnricher()
    result = await enricher.enrich(md)
    assert result == md


async def test_graceful_degradation_on_api_error():
    md = "![spirometry](https://cdn.example.com/spiro.png)"

    async def failing_describe(*args, **kwargs):
        raise RuntimeError("API unavailable")

    with patch("app.services.image_enricher.llm_adapter.describe_image", side_effect=failing_describe):
        enricher = ImageEnricher()
        result = await enricher.enrich(md)

    assert "[IMAGE:" in result
    assert "unavailable" in result or "spirometry" in result
