"""API routes for company details and enrichment triggers."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.schemas.company import (
    CompanyDetailResponse,
    EnrichmentBatchResponse,
    EnrichmentRunResponse,
)
from app.core.config import get_settings
from app.core.exceptions import EntityNotFoundError
from app.db.models.campaign import Campaign, CampaignCompany
from app.db.models.company import Company
from app.db.models.enrichment import EnrichmentRun
from app.db.models.evidence import SourceEvidence
from app.db.session import get_sync_db_session
from app.providers.base import BaseEnrichmentProvider
from app.providers.mock_provider import MockEnrichmentProvider
from app.providers.website_provider import WebsiteEnrichmentProvider
from app.services.enrichment_orchestrator import EnrichmentOrchestrator

router = APIRouter(tags=["Companies & Enrichment"])
settings = get_settings()


def get_default_provider() -> BaseEnrichmentProvider:
    """Dependency returning configured enrichment provider."""
    if settings.LLM_PROVIDER == "mock" or settings.ENVIRONMENT == "testing":
        return MockEnrichmentProvider()
    return WebsiteEnrichmentProvider(timeout_seconds=float(settings.DEFAULT_TIMEOUT_SECONDS))


@router.get("/companies/{company_id}", response_model=CompanyDetailResponse)
def get_company_details(
    company_id: uuid.UUID,
    db: Annotated[Session, Depends(get_sync_db_session)],
) -> CompanyDetailResponse:
    """Fetch company record along with associated source evidence and enrichment history."""
    company = db.scalar(select(Company).where(Company.id == company_id))
    if not company:
        raise EntityNotFoundError(f"Company with ID {company_id} not found")

    evidence_records = (
        db.scalars(
            select(SourceEvidence)
            .where(SourceEvidence.company_id == company_id)
            .order_by(SourceEvidence.retrieved_at.desc())
        ).all()
        or []
    )

    recent_runs = (
        db.scalars(
            select(EnrichmentRun)
            .where(EnrichmentRun.company_id == company_id)
            .order_by(EnrichmentRun.started_at.desc())
            .limit(10)
        ).all()
        or []
    )

    return CompanyDetailResponse(
        id=company.id,
        normalized_domain=company.normalized_domain,
        company_name=company.company_name,
        industry=company.industry,
        employee_range=company.employee_range,
        description=company.description,
        record_status=company.record_status,
        created_at=company.created_at,
        updated_at=company.updated_at,
        evidence=list(evidence_records),
        recent_runs=list(recent_runs),
    )


@router.post("/companies/{company_id}/enrich", response_model=EnrichmentRunResponse)
def enrich_single_company(
    company_id: uuid.UUID,
    db: Annotated[Session, Depends(get_sync_db_session)],
    provider: Annotated[BaseEnrichmentProvider, Depends(get_default_provider)],
    force_refresh: Annotated[bool, Query()] = False,
) -> EnrichmentRunResponse:
    """Trigger enrichment for a single company."""
    company = db.scalar(select(Company).where(Company.id == company_id))
    if not company:
        raise EntityNotFoundError(f"Company with ID {company_id} not found")

    orchestrator = EnrichmentOrchestrator(
        provider=provider,
        max_retries=settings.MAX_RETRIES,
        backoff_factor=0.01 if settings.is_testing else 0.5,
    )

    run = orchestrator.enrich_company(db, company, force_refresh=force_refresh)
    return EnrichmentRunResponse.model_validate(run)


@router.post("/campaigns/{campaign_id}/enrich", response_model=EnrichmentBatchResponse)
def enrich_campaign_companies(
    campaign_id: uuid.UUID,
    db: Annotated[Session, Depends(get_sync_db_session)],
    provider: Annotated[BaseEnrichmentProvider, Depends(get_default_provider)],
    force_refresh: Annotated[bool, Query()] = False,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> EnrichmentBatchResponse:
    """Trigger batch enrichment for companies associated with a campaign."""
    campaign = db.scalar(select(Campaign).where(Campaign.id == campaign_id))
    if not campaign:
        raise EntityNotFoundError(f"Campaign with ID {campaign_id} not found")

    company_ids_subq = (
        select(CampaignCompany.company_id)
        .where(CampaignCompany.campaign_id == campaign_id)
        .limit(limit)
    )

    companies = db.scalars(select(Company).where(Company.id.in_(company_ids_subq))).all()

    orchestrator = EnrichmentOrchestrator(
        provider=provider,
        max_retries=settings.MAX_RETRIES,
        backoff_factor=0.01 if settings.is_testing else 0.5,
    )

    summary = orchestrator.enrich_batch(db, list(companies), force_refresh=force_refresh)

    return EnrichmentBatchResponse(
        total_companies=summary.total_companies,
        succeeded=summary.succeeded,
        failed=summary.failed,
        skipped_fresh=summary.skipped_fresh,
        run_ids=summary.run_ids,
        errors=summary.errors,
    )
