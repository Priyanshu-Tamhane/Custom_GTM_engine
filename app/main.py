"""Main FastAPI application entrypoint."""

import time
import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from app.api.api_router import api_router
from app.api.routes.health import router as health_router
from app.core.config import get_settings
from app.core.exceptions import (
    DuplicateEntityError,
    EntityNotFoundError,
    GTMAppException,
    ValidationError,
)
from app.core.logging import logger, request_id_ctx, setup_logging

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan context for startup and shutdown routines."""
    setup_logging(settings.LOG_LEVEL)
    logger.info(
        f"Starting {settings.PROJECT_NAME} v{settings.VERSION} in {settings.ENVIRONMENT} mode"
    )
    yield
    logger.info("Shutting down GTM Intelligence Engine")


class RequestContextMiddleware:
    """Pure ASGI middleware injecting X-Request-ID and response timing without task groups."""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        req_id = str(uuid.uuid4())
        for name, value in scope.get("headers", []):
            if name.lower() == b"x-request-id":
                req_id = value.decode("utf-8", errors="ignore")
                break

        token = request_id_ctx.set(req_id)
        start_time = time.perf_counter()

        async def send_wrapper(message: dict) -> None:
            if message["type"] == "http.response.start":
                duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
                headers = list(message.get("headers", []))
                headers.append((b"x-request-id", req_id.encode("utf-8")))
                headers.append((b"x-response-time-ms", str(duration_ms).encode("utf-8")))
                message["headers"] = headers
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            request_id_ctx.reset(token)


app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Auditable prospect research, qualification, and evidence-grounded outreach engine.",
    version=settings.VERSION,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Custom context middleware
app.add_middleware(RequestContextMiddleware)


# Exception Handlers
@app.exception_handler(EntityNotFoundError)
async def entity_not_found_handler(request: Request, exc: EntityNotFoundError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={"error": "Not Found", "message": exc.message, "details": exc.details},
    )


@app.exception_handler(DuplicateEntityError)
async def duplicate_entity_handler(request: Request, exc: DuplicateEntityError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={"error": "Conflict", "message": exc.message, "details": exc.details},
    )


@app.exception_handler(ValidationError)
async def validation_error_handler(request: Request, exc: ValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"error": "Validation Error", "message": exc.message, "details": exc.details},
    )


@app.exception_handler(GTMAppException)
async def gtm_generic_handler(request: Request, exc: GTMAppException) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"error": "Bad Request", "message": exc.message, "details": exc.details},
    )


# Root health probes
app.include_router(health_router)

# Versioned API routes
app.include_router(api_router, prefix=settings.API_PREFIX)
