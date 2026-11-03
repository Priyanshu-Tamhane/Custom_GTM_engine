"""Health and readiness check endpoints."""

from datetime import UTC, datetime

import redis
from fastapi import APIRouter, status
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.core.config import get_settings
from app.db.session import sync_engine

router = APIRouter(tags=["Health & Monitoring"])
settings = get_settings()


@router.get("/health", status_code=status.HTTP_200_OK)
def health_check() -> dict:
    """Liveness probe confirming the API process is alive and responsive."""
    return {
        "status": "healthy",
        "service": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "environment": settings.ENVIRONMENT,
        "timestamp": datetime.now(UTC).isoformat(),
    }


@router.get("/ready")
def readiness_check() -> JSONResponse:
    """Readiness probe checking database and cache/broker connectivity."""
    checks: dict[str, str] = {
        "database": "unknown",
        "redis": "unknown",
    }
    all_healthy = True

    # Check Database
    try:
        with sync_engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        checks["database"] = "connected"
    except Exception as exc:  # noqa: BLE001 - catch all connectivity errors for status reporting
        checks["database"] = f"unhealthy: {type(exc).__name__}"
        all_healthy = False

    # Check Redis
    try:
        r = redis.from_url(
            settings.REDIS_URL,
            socket_timeout=0.5,
            socket_connect_timeout=0.5,
        )
        r.ping()
        checks["redis"] = "connected"
    except Exception as exc:  # noqa: BLE001 - catch all connectivity errors for status reporting
        checks["redis"] = f"unhealthy: {type(exc).__name__}"
        all_healthy = False

    status_code = status.HTTP_200_OK if all_healthy else status.HTTP_503_SERVICE_UNAVAILABLE
    return JSONResponse(
        status_code=status_code,
        content={
            "status": "ready" if all_healthy else "degraded",
            "checks": checks,
            "timestamp": datetime.now(UTC).isoformat(),
        },
    )
