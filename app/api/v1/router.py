from fastapi import APIRouter

from app.api.v1.endpoints.analytics import router as analytics_router
from app.api.v1.endpoints.admin_auth import router as admin_auth_router
from app.api.v1.endpoints.admin_users import router as admin_users_router
from app.api.v1.endpoints.auth import router as auth_router
from app.api.v1.endpoints.emr import router as emr_router
from app.api.v1.endpoints.encounters import router as encounters_router
from app.api.v1.endpoints.patients import router as patients_router
from app.api.v1.endpoints.providers import router as providers_router
from app.api.v1.endpoints.rag import router as rag_router
from app.api.v1.endpoints.report import router as report_router
from app.api.v1.endpoints.users import router as users_router

router = APIRouter()

# Provider (doctor) auth
router.include_router(auth_router)

# Admin console auth + user management
router.include_router(admin_auth_router)
router.include_router(admin_users_router)

router.include_router(analytics_router)
router.include_router(rag_router)
router.include_router(emr_router)
router.include_router(report_router)
router.include_router(patients_router)
router.include_router(providers_router)
router.include_router(users_router)
router.include_router(encounters_router)
