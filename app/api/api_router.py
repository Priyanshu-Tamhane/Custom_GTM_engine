"""Top-level API router combining all route modules."""

from fastapi import APIRouter

from app.api.routes.campaigns import router as campaigns_router
from app.api.routes.companies import router as companies_router
from app.api.routes.extraction import router as extraction_router
from app.api.routes.health import router as health_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(campaigns_router)
api_router.include_router(companies_router)
api_router.include_router(extraction_router)
