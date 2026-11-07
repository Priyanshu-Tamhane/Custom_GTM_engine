"""API endpoints for AI fact extraction and verification."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.schemas.extraction import ExtractionResultResponse
from app.core.config import get_settings
from app.db.session import get_sync_db_session
from app.providers.llm.base import BaseLLMProvider
from app.providers.llm.groq_llm import GroqLLMProvider
from app.providers.llm.mock_llm import MockLLMProvider
from app.services.extractor import FactExtractorService

router = APIRouter(tags=["AI Extraction & Verification"])
settings = get_settings()


def get_llm_provider() -> BaseLLMProvider:
    """Dependency providing configured LLM provider (Groq or deterministic Mock)."""
    if settings.LLM_PROVIDER.lower() == "groq" and settings.GROQ_API_KEY:
        return GroqLLMProvider(
            api_key=settings.GROQ_API_KEY.get_secret_value(),
            model_name=settings.GROQ_MODEL,
        )
    return MockLLMProvider()


@router.post("/companies/{company_id}/extract", response_model=ExtractionResultResponse)
def extract_company_facts(
    company_id: uuid.UUID,
    db: Annotated[Session, Depends(get_sync_db_session)],
    llm: Annotated[BaseLLMProvider, Depends(get_llm_provider)],
) -> ExtractionResultResponse:
    """Extract verified facts and qualification signals for a company account from evidence."""
    service = FactExtractorService(db=db, llm_provider=llm)
    return service.extract_company_facts(company_id=company_id)


@router.post("/campaigns/{campaign_id}/extract", response_model=list[ExtractionResultResponse])
def extract_campaign_facts(
    campaign_id: uuid.UUID,
    db: Annotated[Session, Depends(get_sync_db_session)],
    llm: Annotated[BaseLLMProvider, Depends(get_llm_provider)],
) -> list[ExtractionResultResponse]:
    """Run batch extraction across all companies linked to a campaign with partial failure isolation."""
    service = FactExtractorService(db=db, llm_provider=llm)
    return service.extract_campaign_companies(campaign_id=campaign_id)
