"""Thin async adapter over Qwen (OpenAI-compatible) APIs.

All LLM calls are logged to ``llm_calls`` via an injected DB session.
Pass ``db=None`` to skip logging (useful in tests / bootstrap scripts).
"""

from __future__ import annotations

import base64
import time
from typing import TYPE_CHECKING

import httpx
from openai import AsyncOpenAI

from app.core.config import settings

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


def _make_client() -> AsyncOpenAI:
    api_key = settings.QWEN_API_KEY
    if not api_key:
        raise RuntimeError(
            "QWEN_API_KEY is not set. "
            "Add it to your .env file and restart the server."
        )
    return AsyncOpenAI(
        api_key=api_key,
        base_url=settings.QWEN_BASE_URL,
        http_client=httpx.AsyncClient(timeout=60.0),
    )


# Module-level client — recreated whenever the key changes between restarts.
_client: AsyncOpenAI | None = None
_client_api_key: str | None = None


def get_client() -> AsyncOpenAI:
    global _client, _client_api_key
    current_key = settings.QWEN_API_KEY
    if _client is None or _client_api_key != current_key:
        _client = _make_client()
        _client_api_key = current_key
    return _client


async def chat(
    messages: list[dict],
    *,
    model: str | None = None,
    temperature: float = 0.2,
    db: "AsyncSession | None" = None,
    request_id: str | None = None,
    node_name: str | None = None,
) -> str:
    """Send a chat completion request and return the assistant message text."""
    model = model or settings.QWEN_CHAT_MODEL
    start = time.monotonic()
    response = await get_client().chat.completions.create(
        model=model,
        messages=messages,  # type: ignore[arg-type]
        temperature=temperature,
    )
    latency_ms = int((time.monotonic() - start) * 1000)
    content = response.choices[0].message.content or ""

    if db is not None:
        await _log_llm_call(
            db=db,
            request_id=request_id,
            node_name=node_name,
            model_name=model,
            call_type="chat",
            prompt_tokens=response.usage.prompt_tokens if response.usage else None,
            completion_tokens=response.usage.completion_tokens if response.usage else None,
            latency_ms=latency_ms,
        )
    return content


_EMBED_BATCH_SIZE = 10  # Qwen embedding API limit per request


async def embed(
    texts: list[str],
    *,
    model: str | None = None,
    db: "AsyncSession | None" = None,
    request_id: str | None = None,
) -> list[list[float]]:
    """Embed a batch of texts; auto-splits into batches of ≤10 (Qwen API limit)."""
    model = model or settings.QWEN_EMBEDDING_MODEL
    all_vectors: list[list[float]] = []
    total_prompt_tokens = 0
    total_latency_ms = 0

    for i in range(0, len(texts), _EMBED_BATCH_SIZE):
        batch = texts[i: i + _EMBED_BATCH_SIZE]
        start = time.monotonic()
        response = await get_client().embeddings.create(model=model, input=batch)
        total_latency_ms += int((time.monotonic() - start) * 1000)
        batch_vectors = [item.embedding for item in sorted(response.data, key=lambda x: x.index)]
        all_vectors.extend(batch_vectors)
        if response.usage:
            total_prompt_tokens += response.usage.prompt_tokens

    vectors = all_vectors
    latency_ms = total_latency_ms

    if db is not None:
        await _log_llm_call(
            db=db,
            request_id=request_id,
            node_name="embed",
            model_name=model,
            call_type="embed",
            prompt_tokens=total_prompt_tokens or None,
            completion_tokens=None,
            latency_ms=latency_ms,
        )
    return vectors


async def describe_image(
    image_url: str,
    prompt: str = "Describe this clinical image in detail for medical documentation.",
    *,
    model: str | None = None,
    db: "AsyncSession | None" = None,
    request_id: str | None = None,
) -> str:
    """Use Qwen-VL to generate a text description of a clinical image.

    ``image_url`` can be a remote HTTPS URL or a local path (which will be
    base64-encoded and sent as a data URI).
    """
    model = model or settings.QWEN_VL_MODEL

    if image_url.startswith("http"):
        image_content: dict = {"type": "image_url", "image_url": {"url": image_url}}
    else:
        import aiofiles

        async with aiofiles.open(image_url, "rb") as f:
            raw = await f.read()
        b64 = base64.b64encode(raw).decode()
        ext = image_url.rsplit(".", 1)[-1].lower()
        mime = f"image/{ext}" if ext in {"jpg", "jpeg", "png", "webp", "gif"} else "image/jpeg"
        image_content = {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}}

    messages = [
        {
            "role": "user",
            "content": [image_content, {"type": "text", "text": prompt}],
        }
    ]

    start = time.monotonic()
    response = await get_client().chat.completions.create(model=model, messages=messages)  # type: ignore[arg-type]
    latency_ms = int((time.monotonic() - start) * 1000)
    description = response.choices[0].message.content or ""

    if db is not None:
        await _log_llm_call(
            db=db,
            request_id=request_id,
            node_name="describe_image",
            model_name=model,
            call_type="vision",
            prompt_tokens=response.usage.prompt_tokens if response.usage else None,
            completion_tokens=response.usage.completion_tokens if response.usage else None,
            latency_ms=latency_ms,
        )
    return description


async def _log_llm_call(
    db: "AsyncSession",
    *,
    request_id: str | None,
    node_name: str | None,
    model_name: str,
    call_type: str,
    prompt_tokens: int | None,
    completion_tokens: int | None,
    latency_ms: int,
) -> None:
    from app.models.ops import LlmCall

    record = LlmCall(
        request_id=request_id,
        graph_node_name=node_name,
        model_name=model_name,
        call_type=call_type,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        latency_ms=latency_ms,
    )
    db.add(record)
    await db.flush()
