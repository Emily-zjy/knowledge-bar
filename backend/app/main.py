from __future__ import annotations

import logging
import time
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.ai import router as ai_router
from app.api.mindmap import router as mindmap_router
from app.core.config import settings
from app.db.store import init_db
from app.models.ai import ApiError, ApiResponse

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("knowledge_bar.api")

app = FastAPI(title="Knowledge Bar API", version="0.2.0")

init_db()

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or str(uuid4())
    request.state.request_id = request_id
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        logger.exception(
            "request_failed",
            extra={"request_id": request_id, "path": request.url.path, "elapsed_ms": elapsed_ms},
        )
        raise

    elapsed_ms = int((time.perf_counter() - started) * 1000)
    response.headers["X-Request-ID"] = request_id
    logger.info(
        "request_completed",
        extra={
            "request_id": request_id,
            "path": request.url.path,
            "method": request.method,
            "status_code": response.status_code,
            "elapsed_ms": elapsed_ms,
        },
    )
    return response


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    _ = exc
    return JSONResponse(
        status_code=422,
        content=ApiResponse(
            success=False,
            error=ApiError(code="VALIDATION_ERROR", message="Request validation failed."),
        ).model_dump(),
        headers={"X-Request-ID": getattr(request.state, "request_id", "")},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception(
        "unhandled_exception",
        extra={"request_id": getattr(request.state, "request_id", ""), "error_type": type(exc).__name__},
    )
    return JSONResponse(
        status_code=500,
        content=ApiResponse(
            success=False,
            error=ApiError(code="INTERNAL_SERVER_ERROR", message="Unexpected server error."),
        ).model_dump(),
        headers={"X-Request-ID": getattr(request.state, "request_id", "")},
    )


app.include_router(ai_router, prefix="/api")
app.include_router(mindmap_router, prefix="/api")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "knowledge-bar-api"}
