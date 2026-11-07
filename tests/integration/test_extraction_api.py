"""Integration tests for AI extraction API route handlers."""

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy.orm import Session

from app.api.routes.extraction import extract_campaign_facts, extract_company_facts
from app.core.exceptions import EntityNotFoundError
from app.db.models.campaign import Campaign, CampaignCompany
from app.db.models.company import Company
from app.db.models.evidence import SourceEvidence
from app.providers.llm.mock_llm import MockLLMProvider


def test_extract_company_facts_route_success(db_session: Session):
    """Verify route extracts facts, updates company status, and returns complete schema."""
    company = Company(
        normalized_domain="vanta.com",
        company_name="Vanta",
        record_status="imported",
    )
    db_session.add(company)
    db_session.commit()

    ev_id = uuid.uuid4()
    evidence = SourceEvidence(
        id=ev_id,
        company_id=company.id,
        source_type="website",
        source_url="https://vanta.com",
        retrieved_at=datetime.now(UTC),
        content_hash="vanta_hash_123",
        excerpt="Vanta is the leader in automated compliance and security monitoring for B2B SaaS.",
    )
    db_session.add(evidence)
    db_session.commit()

    llm = MockLLMProvider()
    response = extract_company_facts(
        company_id=company.id,
        db=db_session,
        llm=llm,
    )

    assert response.company_id == company.id
    assert response.extracted_facts.company_name == "Vanta"
    assert response.extracted_facts.industry.value == "B2B SaaS"
    assert response.extracted_facts.needs_human_review is False
    assert response.input_tokens > 0
    assert response.output_tokens > 0
    assert response.latency_ms > 0
    assert response.estimated_cost_usd > 0

    # Verify company is now facts_extracted
    db_session.refresh(company)
    assert company.record_status == "facts_extracted"


def test_extract_company_facts_route_not_found(db_session: Session):
    """Verify route raises EntityNotFoundError when company doesn't exist."""
    llm = MockLLMProvider()
    with pytest.raises(EntityNotFoundError):
        extract_company_facts(
            company_id=uuid.uuid4(),
            db=db_session,
            llm=llm,
        )


def test_extract_campaign_facts_route_batch(db_session: Session):
    """Verify route extracts facts for all accounts linked to a campaign."""
    campaign = Campaign(
        name="Security SaaS Batch Campaign",
        product_description="AI Support Automation for modern tech companies",
        icp_config={"industries": ["B2B SaaS"]},
    )
    db_session.add(campaign)
    db_session.commit()

    comp1 = Company(normalized_domain="vanta.com", company_name="Vanta")
    comp2 = Company(normalized_domain="incident.io", company_name="incident.io")
    db_session.add_all([comp1, comp2])
    db_session.commit()

    db_session.add_all([
        CampaignCompany(campaign_id=campaign.id, company_id=comp1.id),
        CampaignCompany(campaign_id=campaign.id, company_id=comp2.id),
    ])

    ev1 = SourceEvidence(
        id=uuid.uuid4(),
        company_id=comp1.id,
        source_type="website",
        content_hash="h1",
        excerpt="Vanta security platform.",
    )
    ev2 = SourceEvidence(
        id=uuid.uuid4(),
        company_id=comp2.id,
        source_type="website",
        content_hash="h2",
        excerpt="incident.io incident response platform.",
    )
    db_session.add_all([ev1, ev2])
    db_session.commit()

    llm = MockLLMProvider()
    responses = extract_campaign_facts(
        campaign_id=campaign.id,
        db=db_session,
        llm=llm,
    )

    assert len(responses) == 2
    domains = {r.extracted_facts.company_name for r in responses}
    assert "Vanta" in domains
    assert "incident.io" in domains
