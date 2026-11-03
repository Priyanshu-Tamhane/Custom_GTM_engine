"""Unit tests for SQLAlchemy models and constraints."""

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import (
    Campaign,
    CampaignCompany,
    Company,
    IntegrationEvent,
    Job,
    OutreachDraft,
    Qualification,
    ReviewDecision,
    SourceEvidence,
)


def test_company_creation_and_unique_domain(db_session: Session):
    company1 = Company(
        normalized_domain="example.com",
        company_name="Example Inc",
        industry="B2B SaaS",
        employee_range="50-100",
    )
    db_session.add(company1)
    db_session.commit()

    assert isinstance(company1.id, uuid.UUID)
    assert company1.record_status == "imported"

    # Verify duplicate domain constraint
    company2 = Company(
        normalized_domain="example.com",
        company_name="Example Duplicate",
    )
    db_session.add(company2)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_campaign_and_association(db_session: Session):
    campaign = Campaign(
        name="Test Campaign",
        product_description="Test Product Description",
        icp_config={"target_industries": ["B2B SaaS"]},
        rubric_version="v1",
    )
    company = Company(
        normalized_domain="testco.com",
        company_name="TestCo",
    )
    db_session.add_all([campaign, company])
    db_session.commit()

    association = CampaignCompany(
        campaign_id=campaign.id,
        company_id=company.id,
        status="pending",
    )
    db_session.add(association)
    db_session.commit()

    res = db_session.execute(
        select(CampaignCompany).where(CampaignCompany.campaign_id == campaign.id)
    )
    fetched = res.scalar_one()
    assert fetched.company_id == company.id


def test_source_evidence_and_qualification(db_session: Session):
    campaign = Campaign(name="Camp 2", product_description="Desc", icp_config={})
    company = Company(normalized_domain="evidenceco.com", company_name="Evidence Co")
    db_session.add_all([campaign, company])
    db_session.commit()

    evidence = SourceEvidence(
        company_id=company.id,
        source_type="website",
        source_url="https://evidenceco.com/support",
        content_hash="abc123hash",
        excerpt="We offer 24/7 dedicated customer support.",
        field_names_supported=["public support/help center"],
    )
    db_session.add(evidence)
    db_session.commit()

    qualification = Qualification(
        campaign_id=campaign.id,
        company_id=company.id,
        score=85.0,
        score_breakdown={
            "segment_fit": 30,
            "size_fit": 15,
            "use_case_fit": 25,
            "evidence_quality": 10,
        },
        rubric_version="v1",
        evidence_ids=[str(evidence.id)],
        status="scored",
    )
    db_session.add(qualification)
    db_session.commit()

    assert qualification.score == 85.0
    assert str(evidence.id) in qualification.evidence_ids


def test_draft_and_review_decision(db_session: Session):
    campaign = Campaign(name="Camp 3", product_description="Desc", icp_config={})
    company = Company(normalized_domain="draftco.com", company_name="Draft Co")
    db_session.add_all([campaign, company])
    db_session.commit()

    draft = OutreachDraft(
        campaign_id=campaign.id,
        company_id=company.id,
        subject="Quick question about Draft Co",
        body="Saw your support team expansion...",
        claims_used=[{"claim": "support team expansion", "evidence_ids": ["ev_1"]}],
        model_name="mock-llm",
        prompt_version="v1",
    )
    db_session.add(draft)
    db_session.commit()

    review = ReviewDecision(
        draft_id=draft.id,
        reviewer_id="reviewer_1",
        decision="approved",
        reason="Claims verified against support portal evidence.",
    )
    db_session.add(review)
    db_session.commit()

    assert review.decision == "approved"
    assert review.draft_id == draft.id


def test_job_and_integration_event(db_session: Session):
    job = Job(
        job_type="import",
        status="queued",
        idempotency_key="import_job_key_1",
        payload_reference={"filename": "companies.csv"},
    )
    db_session.add(job)
    db_session.commit()

    duplicate_job = Job(
        job_type="import",
        status="queued",
        idempotency_key="import_job_key_1",
    )
    db_session.add(duplicate_job)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

    event = IntegrationEvent(
        destination="csv_export",
        entity_type="batch",
        entity_id=uuid.uuid4(),
        operation="export",
        idempotency_key="export_key_1",
        status="pending",
    )
    db_session.add(event)
    db_session.commit()
    assert event.status == "pending"
