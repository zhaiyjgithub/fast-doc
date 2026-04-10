"""RAG endpoints — markdown ingestion, PDF upload, image upload, document management."""

from __future__ import annotations

import base64
import os
import tempfile
import uuid
from pathlib import Path
from typing import Annotated

import aiofiles
from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import CurrentPrincipal, require_admin, require_doctor_or_admin
from app.db.session import get_db
from app.models.rag import KnowledgeChunk, KnowledgeDocument
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
    _user: Annotated["CurrentPrincipal", Depends(require_admin)],
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
    _user: "CurrentPrincipal" = Depends(require_admin),
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


# ---------------------------------------------------------------------------
# Background helper for PDF ingestion
# ---------------------------------------------------------------------------

async def _ingest_pdf_background(
    tmp_path: str,
    document_id: str,
    source_namespace: str,
    title: str,
    version: str,
    patient_id: str | None,
    guideline_type: str,
) -> None:
    from app.db.session import AsyncSessionLocal
    from app.services.guideline_ingestion import GuidelineIngestionService, GuidelinePDFSpec

    async with AsyncSessionLocal() as bg_db:
        try:
            svc = GuidelineIngestionService(bg_db)
            spec = GuidelinePDFSpec(
                path=Path(tmp_path),
                title=title,
                version=version or "v1",
            )
            await svc.ingest_pdf_files_bulk([spec])
            result = await bg_db.execute(
                select(KnowledgeDocument).where(KnowledgeDocument.id == document_id)
            )
            doc = result.scalars().first()
            if doc:
                doc.status = "done"
            await bg_db.commit()
        except Exception:
            await bg_db.rollback()
            async with AsyncSessionLocal() as err_db:
                result = await err_db.execute(
                    select(KnowledgeDocument).where(KnowledgeDocument.id == document_id)
                )
                doc = result.scalars().first()
                if doc:
                    doc.status = "failed"
                await err_db.commit()
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


# ---------------------------------------------------------------------------
# POST /pdf
# ---------------------------------------------------------------------------

@router.post("/pdf", status_code=status.HTTP_202_ACCEPTED)
async def upload_pdf(
    _user: Annotated["CurrentPrincipal", Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    source_namespace: str = Form(...),
    title: str = Form(...),
    version: str = Form(""),
    patient_id: str | None = Form(None),
    guideline_type: str = Form("general"),
    effective_from: str | None = Form(None),
):
    """Upload a PDF for background ingestion via MinerU.

    Returns immediately with *document_id*. Poll
    ``GET /v1/rag/documents/{id}`` to check status.
    """
    if source_namespace == "patient" and patient_id is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="patient_id is required when source_namespace is 'patient'",
        )

    suffix = Path(file.filename or "upload.pdf").suffix or ".pdf"
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    tmp_path = tmp.name
    tmp.close()

    async with aiofiles.open(tmp_path, "wb") as f:
        content = await file.read()
        await f.write(content)

    doc = KnowledgeDocument(
        source_namespace=source_namespace,
        title=title,
        version=version or "",
        status="pending",
        is_active=True,
    )
    db.add(doc)
    await db.flush()
    document_id = str(doc.id)

    background_tasks.add_task(
        _ingest_pdf_background,
        tmp_path=tmp_path,
        document_id=document_id,
        source_namespace=source_namespace,
        title=title,
        version=version,
        patient_id=patient_id,
        guideline_type=guideline_type,
    )

    return {"document_id": document_id, "status": "pending", "message": "PDF queued for processing"}


# ---------------------------------------------------------------------------
# POST /image
# ---------------------------------------------------------------------------

@router.post("/image", status_code=status.HTTP_201_CREATED)
async def upload_image(
    _user: Annotated["CurrentPrincipal", Depends(require_doctor_or_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    file: UploadFile = File(...),
    patient_id: str = Form(...),
    section_hint: str = Form("Clinical Document"),
):
    """Upload a clinical image (PNG/JPG/WEBP).

    Qwen-VL generates a text description which is stored as a patient
    knowledge chunk.
    """
    content_type = file.content_type or ""
    filename = file.filename or ""
    allowed_ext = {".jpg", ".jpeg", ".png", ".webp"}
    if not content_type.startswith("image/") and Path(filename).suffix.lower() not in allowed_ext:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="File must be an image (jpg, jpeg, png, webp)",
        )

    content = await file.read()
    b64 = base64.b64encode(content).decode()
    mime = content_type if content_type.startswith("image/") else "image/jpeg"
    data_url = f"data:{mime};base64,{b64}"

    from app.services import llm_adapter
    description = await llm_adapter.describe_image(
        data_url,
        f"Describe this clinical image for medical documentation. Context: {section_hint}",
        db=db,
    )

    svc = MarkdownIngestionService(db)
    markdown = f"# {section_hint}\n\n[IMAGE DESCRIPTION — {section_hint}]:\n{description}\n"
    patient_uuid = uuid.UUID(patient_id)
    doc = await svc.ingest_markdown(
        markdown_text=markdown,
        source_namespace="patient",
        title=f"{section_hint} — {filename}",
        patient_id=patient_uuid,
    )

    return {
        "document_id": str(doc.id),
        "description_preview": description[:200],
    }


# ---------------------------------------------------------------------------
# GET /documents
# ---------------------------------------------------------------------------

@router.get("/documents")
async def list_documents(
    _user: Annotated["CurrentPrincipal", Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    source_namespace: str | None = None,
    page: int = 1,
    page_size: int = 20,
):
    """List KnowledgeDocuments with optional namespace filter and pagination."""
    query = select(KnowledgeDocument)
    count_query = select(func.count()).select_from(KnowledgeDocument)
    if source_namespace:
        query = query.where(KnowledgeDocument.source_namespace == source_namespace)
        count_query = count_query.where(KnowledgeDocument.source_namespace == source_namespace)

    total = (await db.execute(count_query)).scalar()
    items = (
        await db.execute(
            query.order_by(KnowledgeDocument.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).scalars().all()

    return {
        "items": [
            {
                "id": str(d.id),
                "title": d.title,
                "source_namespace": d.source_namespace,
                "version": d.version,
                "status": d.status,
                "is_active": d.is_active,
                "created_at": d.created_at.isoformat() if d.created_at else None,
            }
            for d in items
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


# ---------------------------------------------------------------------------
# GET /documents/{document_id}
# ---------------------------------------------------------------------------

@router.get("/documents/{document_id}")
async def get_document(
    document_id: str,
    _user: Annotated["CurrentPrincipal", Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Retrieve a single KnowledgeDocument by ID (for status polling)."""
    result = await db.execute(select(KnowledgeDocument).where(KnowledgeDocument.id == document_id))
    doc = result.scalars().first()
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")

    return {
        "id": str(doc.id),
        "title": doc.title,
        "source_namespace": doc.source_namespace,
        "version": doc.version,
        "status": doc.status,
        "is_active": doc.is_active,
        "created_at": doc.created_at.isoformat() if doc.created_at else None,
    }


# ---------------------------------------------------------------------------
# DELETE /documents/{document_id}
# ---------------------------------------------------------------------------

@router.delete("/documents/{document_id}", status_code=status.HTTP_200_OK)
async def delete_document(
    document_id: str,
    _user: Annotated["CurrentPrincipal", Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Soft-delete a document and deactivate all its chunks."""
    result = await db.execute(select(KnowledgeDocument).where(KnowledgeDocument.id == document_id))
    doc = result.scalars().first()
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")

    doc.is_active = False
    await db.execute(
        update(KnowledgeChunk)
        .where(KnowledgeChunk.document_id == doc.id)
        .values(is_active=False)
    )
    await db.flush()
    return {"document_id": document_id, "status": "deleted"}
