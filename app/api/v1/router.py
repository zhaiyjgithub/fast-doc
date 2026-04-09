from fastapi import APIRouter

from app.api.v1.endpoints.emr import router as emr_router
from app.api.v1.endpoints.rag import router as rag_router

router = APIRouter()

router.include_router(rag_router)
router.include_router(emr_router)
