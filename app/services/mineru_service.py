"""MinerU Token-based 精准解析 API client (v4).

Supports two submission modes:
  - remote_url: Submit a publicly accessible URL directly.
  - local_file:  Upload via pre-signed OSS URL (batch upload flow).

Both modes poll for completion and return the full markdown text extracted
from the result ZIP's ``full.md`` file.
"""

from __future__ import annotations

import asyncio
import io
import zipfile
from pathlib import Path

import httpx

from app.core.config import settings


class MinerUError(RuntimeError):
    pass


class MinerUService:
    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key or settings.MINERU_API_KEY
        self._headers = {"Authorization": f"Bearer {self._api_key}"}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def extract_from_url(self, url: str) -> str:
        """Submit a remote URL for extraction; return full markdown text."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                settings.MINERU_SINGLE_URL,
                headers=self._headers,
                json={
                    "url": url,
                    "is_ocr": True,
                    "language": settings.MINERU_LANGUAGE,
                    "model_version": settings.MINERU_MODEL_VERSION,
                    "enable_formula": False,
                    "layout_model": "doclayout_yolo",
                },
            )
            resp.raise_for_status()
            data = resp.json()

        task_id = data.get("data", {}).get("task_id") or data.get("task_id")
        if not task_id:
            raise MinerUError(f"No task_id in MinerU response: {data}")

        zip_url = await self._poll_single(task_id)
        return await self._download_full_md(zip_url)

    async def extract_local_files(self, file_paths: list[Path]) -> list[str]:
        """Upload local PDFs via pre-signed OSS URLs; return list of markdown texts."""
        async with httpx.AsyncClient(timeout=60.0) as client:
            # Step 1: Request batch upload URLs
            resp = await client.post(
                settings.MINERU_BATCH_UPLOAD_URL,
                headers=self._headers,
                json={
                    "files": [
                        {"name": p.name, "is_ocr": True, "language": settings.MINERU_LANGUAGE}
                        for p in file_paths
                    ]
                },
            )
            resp.raise_for_status()
            batch_data = resp.json()

        file_infos = batch_data.get("data", {}).get("files", [])
        if not file_infos:
            raise MinerUError(f"No file upload URLs returned: {batch_data}")

        # Step 2: Upload each file to its pre-signed URL via PUT
        async with httpx.AsyncClient(timeout=120.0) as client:
            for path, info in zip(file_paths, file_infos):
                put_url = info.get("url")
                if not put_url:
                    raise MinerUError(f"Missing pre-signed URL for {path.name}")
                file_bytes = path.read_bytes()
                upload_resp = await client.put(put_url, content=file_bytes)
                upload_resp.raise_for_status()

        batch_id = batch_data.get("data", {}).get("batch_id")
        if not batch_id:
            raise MinerUError(f"No batch_id in MinerU response: {batch_data}")

        zip_urls = await self._poll_batch(batch_id)
        results: list[str] = []
        for zip_url in zip_urls:
            md = await self._download_full_md(zip_url)
            results.append(md)
        return results

    # ------------------------------------------------------------------
    # Polling helpers
    # ------------------------------------------------------------------

    async def _poll_single(self, task_id: str) -> str:
        """Poll single-task endpoint until done; return full_zip_url."""
        poll_url = settings.MINERU_SINGLE_POLL_URL.format(task_id=task_id)
        deadline = asyncio.get_event_loop().time() + settings.MINERU_MAX_WAIT
        async with httpx.AsyncClient(timeout=30.0) as client:
            while asyncio.get_event_loop().time() < deadline:
                await asyncio.sleep(settings.MINERU_POLL_INTERVAL)
                resp = await client.get(poll_url, headers=self._headers)
                resp.raise_for_status()
                data = resp.json().get("data", {})
                state = data.get("state", "")
                if state == "done":
                    zip_url = data.get("full_zip_url")
                    if not zip_url:
                        raise MinerUError("Task done but no full_zip_url")
                    return zip_url
                if state in ("failed", "error"):
                    raise MinerUError(f"MinerU task failed: {data}")
        raise MinerUError(f"MinerU task {task_id} timed out after {settings.MINERU_MAX_WAIT}s")

    async def _poll_batch(self, batch_id: str) -> list[str]:
        """Poll batch endpoint until all files are done; return list of full_zip_urls."""
        poll_url = settings.MINERU_BATCH_POLL_URL.format(batch_id=batch_id)
        deadline = asyncio.get_event_loop().time() + settings.MINERU_MAX_WAIT
        async with httpx.AsyncClient(timeout=30.0) as client:
            while asyncio.get_event_loop().time() < deadline:
                await asyncio.sleep(settings.MINERU_POLL_INTERVAL)
                resp = await client.get(poll_url, headers=self._headers)
                resp.raise_for_status()
                data = resp.json().get("data", {})
                files = data.get("files", [])
                states = [f.get("state", "") for f in files]
                # waiting-file: still uploading to OSS — keep waiting
                if any(s in ("pending", "running", "waiting-file") for s in states):
                    continue
                if any(s in ("failed", "error") for s in states):
                    raise MinerUError(f"One or more batch files failed: {data}")
                # All done
                zip_urls = [f["full_zip_url"] for f in files if f.get("full_zip_url")]
                return zip_urls
        raise MinerUError(f"MinerU batch {batch_id} timed out after {settings.MINERU_MAX_WAIT}s")

    # ------------------------------------------------------------------
    # Download helper
    # ------------------------------------------------------------------

    async def _download_full_md(self, zip_url: str) -> str:
        """Download the result ZIP and extract the ``full.md`` file contents."""
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.get(zip_url)
            resp.raise_for_status()
            zip_bytes = resp.content

        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            md_names = [n for n in zf.namelist() if n.endswith("full.md")]
            if not md_names:
                raise MinerUError(f"No full.md found in ZIP. Contents: {zf.namelist()}")
            return zf.read(md_names[0]).decode("utf-8")
