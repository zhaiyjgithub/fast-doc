"""ImageEnricher — replaces MinerU image tags with Qwen-VL descriptions.

Pipeline:
  1. Parse all ``![alt](url)`` tags from the markdown.
  2. Classify each image as clinical or decorative using simple heuristics.
  3. For clinical images, call Qwen-VL to generate a text description.
  4. Replace image tags with ``[IMAGE: <description>]`` blocks.
  5. Return the enriched markdown.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from app.core.config import settings
from app.services import llm_adapter

if TYPE_CHECKING:
    pass

# Regex for markdown image tags
_IMG_PATTERN = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")

# CDN / decorative image URL keywords — skip these
_DECORATIVE_HINTS = (
    "logo",
    "banner",
    "icon",
    "avatar",
    "badge",
    "decoration",
    "background",
    "header",
    "footer",
    "watermark",
)


class ImageEnricher:
    """Replace image markdown tags with textual descriptions."""

    def __init__(self, db=None, request_id: str | None = None) -> None:
        self._db = db
        self._request_id = request_id

    def _is_decorative(self, alt: str, url: str) -> bool:
        combined = (alt + " " + url).lower()
        return any(hint in combined for hint in _DECORATIVE_HINTS)

    async def enrich(self, markdown_text: str) -> str:
        """Return markdown with all clinical images replaced by text descriptions."""
        if not settings.IMAGE_DESCRIPTION_ENABLED:
            return markdown_text

        matches = list(_IMG_PATTERN.finditer(markdown_text))
        if not matches:
            return markdown_text

        # Process in order, building replacement map
        replacements: list[tuple[int, int, str]] = []
        for m in matches:
            alt, url = m.group(1), m.group(2)
            if self._is_decorative(alt, url):
                replacements.append((m.start(), m.end(), ""))
                continue
            try:
                description = await llm_adapter.describe_image(
                    url,
                    prompt=(
                        "You are a medical documentation assistant. "
                        "Describe this clinical image in detail for an EMR note. "
                        "Focus on clinically relevant findings."
                    ),
                    db=self._db,
                    request_id=self._request_id,
                )
                replacement = f"[IMAGE: {description}]"
            except Exception as exc:
                # Graceful degradation: keep original alt text
                replacement = f"[IMAGE: {alt or 'clinical image — description unavailable'}]"

            replacements.append((m.start(), m.end(), replacement))

        # Apply replacements in reverse order to preserve offsets
        result = markdown_text
        for start, end, rep in reversed(replacements):
            result = result[:start] + rep + result[end:]

        return result
