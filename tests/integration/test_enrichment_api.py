"""Integration tests for Company details and Enrichment API routes."""

import uuid

from sqlalchemy.orm import Session

from app.api.routes.companies import (
    enrich_campaign_companies,
    enrich_single_company,
    get_company_details,
)
from app.core.exceptions import EntityNotFoundError
from app.db.models.campaign import Campaign, CampaignCompany
from app.db.models.company import Company
from app.providers.mock_provider import MockEnrichmentProvider


def test_get_company_details_empty(db_session: Session):
    company = Company(
        normalized_domain="testcomp.io",
        company_name="Test Company",
        industry="B2B SaaS",
    )
    db_session.add(company)
    db_session.commit()

    detail = get_company_details(company_id=company.id, db=db_session)
    assert detail.id == company.id
    assert detail.normalized_domain == "testcomp.io"
    assert len(detail.evidence) == 0
    assert len(detail.recent_runs) == 0


def test_get_nonexistent_company_raises_404(db_session: Session):
    import pytest

    fake_id = uuid.uuid4()
    with pytest.raises(EntityNotFoundError, match="not found"):
        get_company_details(company_id=fake_id, db=db_session)


def test_enrich_single_company_route(db_session: Session):
    company = Company(
        normalized_domain="vanta.com",
        company_name="Vanta",
    )
    db_session.add(company)
    db_session.commit()

    provider = MockEnrichmentProvider()
    run = enrich_single_company(
        company_id=company.id,
        db=db_session,
        provider=provider,
    )

    assert run.status == "succeeded"
    assert run.attempt_count == 1

    # Verify company details now reflect the new evidence
    detail = get_company_details(company_id=company.id, db=db_session)
    assert detail.record_status == "enriched"
    assert len(detail.evidence) == 1
    assert "public support/help center" in detail.evidence[0].field_names_supported
    assert len(detail.recent_runs) == 1


def test_enrich_campaign_companies_batch(db_session: Session):
    campaign = Campaign(name="Batch Camp", product_description="Desc for bot")
    c1 = Company(normalized_domain="incident.io", company_name="IncidentIO")
    c2 = Company(normalized_domain="linear.app", company_name="Linear")
    db_session.add_all([campaign, c1, c2])
    db_session.commit()

    # Link both to campaign
    db_session.add_all(
        [
            CampaignCompany(campaign_id=campaign.id, company_id=c1.id, status="pending"),
            CampaignCompany(campaign_id=campaign.id, company_id=c2.id, status="pending"),
        ]
    )
    db_session.commit()

    provider = MockEnrichmentProvider()
    summary = enrich_campaign_companies(
        campaign_id=campaign.id,
        db=db_session,
        provider=provider,
    )

    assert summary.total_companies == 2
    assert summary.succeeded == 2
    assert summary.failed == 0
    assert len(summary.run_ids) == 2

    # Verify both companies have evidence stored
    d1 = get_company_details(company_id=c1.id, db=db_session)
    d2 = get_company_details(company_id=c2.id, db=db_session)
    assert len(d1.evidence) == 1
    assert len(d2.evidence) == 1
