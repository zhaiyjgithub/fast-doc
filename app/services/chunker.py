"""DocumentChunker — splits text into overlapping character-based chunks."""

from __future__ import annotations

import hashlib


class DocumentChunker:
    """Split text into overlapping character-level chunks with SHA256 dedup."""

    def __init__(self, chunk_size: int = 1000, overlap: int = 200) -> None:
        self.chunk_size = chunk_size
        self.overlap = overlap

    def split(self, text: str) -> list[dict]:
        """Return list of dicts with ``chunk_text``, ``chunk_index``, ``content_hash``."""
        chunks: list[dict] = []
        start = 0
        index = 0
        while start < len(text):
            end = start + self.chunk_size
            chunk_text = text[start:end].strip()
            if chunk_text:
                content_hash = hashlib.sha256(chunk_text.encode()).hexdigest()
                chunks.append(
                    {
                        "chunk_text": chunk_text,
                        "chunk_index": index,
                        "content_hash": content_hash,
                    }
                )
                index += 1
            if end >= len(text):
                break
            start = end - self.overlap
        return chunks
