"""POST /v1/rag/markdown — ingest a markdown document into RAG."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.services.markdown_ingestion import MarkdownIngestionService

router = APIRouter(prefix="/rag", tags=["rag"])


class MarkdownIngestRequest(BaseModel):
    markdown_text: str
    title: str
    source_namespace: str = "guideline"  # "patient" | "guideline"
    source_file: str | None = None
    version: str | None = None
    patient_id: str | None = None
    extra_metadata: dict | None = None
    request_id: str | None = None


class MarkdownIngestResponse(BaseModel):
    document_id: str
    title: str
    source_namespace: str
    message: str


@router.post("/markdown", response_model=MarkdownIngestResponse, status_code=status.HTTP_201_CREATED)
async def ingest_markdown_json(
    body: MarkdownIngestRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> MarkdownIngestResponse:
    """Ingest a markdown document via JSON body."""
    patient_uuid = uuid.UUID(body.patient_id) if body.patient_id else None
    svc = MarkdownIngestionService(db)
    try:
        doc = await svc.ingest_markdown(
            markdown_text=body.markdown_text,
            title=body.title,
            source_namespace=body.source_namespace,
            source_file=body.source_file,
            version=body.version,
            patient_id=patient_uuid,
            extra_metadata=body.extra_metadata,
            request_id=body.request_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    return MarkdownIngestResponse(
        document_id=str(doc.id),
        title=doc.title,
        source_namespace=doc.source_namespace,
        message="Ingestion complete",
    )


@router.post(
    "/markdown/upload",
    response_model=MarkdownIngestResponse,
    status_code=status.HTTP_201_CREATED,
)
async def ingest_markdown_upload(
    file: Annotated[UploadFile, File(description="Markdown file (.md)")],
    title: Annotated[str, Form()],
    source_namespace: Annotated[str, Form()] = "guideline",
    source_file: Annotated[str | None, Form()] = None,
    version: Annotated[str | None, Form()] = None,
    patient_id: Annotated[str | None, Form()] = None,
    request_id: Annotated[str | None, Form()] = None,
    db: AsyncSession = Depends(get_db),
) -> MarkdownIngestResponse:
    """Ingest a markdown document via multipart file upload."""
    content = await file.read()
    markdown_text = content.decode("utf-8")
    patient_uuid = uuid.UUID(patient_id) if patient_id else None
    svc = MarkdownIngestionService(db)
    try:
        doc = await svc.ingest_markdown(
            markdown_text=markdown_text,
            title=title,
            source_namespace=source_namespace,
            source_file=source_file or file.filename,
            version=version,
            patient_id=patient_uuid,
            request_id=request_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    return MarkdownIngestResponse(
        document_id=str(doc.id),
        title=doc.title,
        source_namespace=doc.source_namespace,
        message="Ingestion complete",
    )
