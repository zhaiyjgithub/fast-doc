from fastapi import FastAPI

from app.api.v1.router import router as v1_router
from app.core.observability import (
    RequestLoggingMiddleware,
    setup_observability,
    unhandled_exception_handler,
)

setup_observability()

app = FastAPI(title="AI EMR Backend", version="0.1.0")
app.add_middleware(RequestLoggingMiddleware)
app.add_exception_handler(Exception, unhandled_exception_handler)

app.include_router(v1_router, prefix="/v1")


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
