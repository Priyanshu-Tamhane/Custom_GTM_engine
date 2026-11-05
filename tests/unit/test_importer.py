"""Unit tests for CSV import service and deduplication."""

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import ValidationError
from app.db.models.campaign import Campaign
from app.db.models.company import Company
from app.services.importer import CSVImportService


@pytest.fixture
def test_campaign(db_session: Session) -> Campaign:
    campaign = Campaign(
        name="Support Automation B2B",
        product_description="AI Support Bot",
        icp_config={"employee_range": [20, 300]},
        rubric_version="v1",
    )
    db_session.add(campaign)
    db_session.commit()
    db_session.refresh(campaign)
    return campaign


def test_import_clean_csv(db_session: Session, test_campaign: Campaign):
    csv_data = """company_name,domain,industry,employee_count,source_url,notes
Linear,https://linear.app,B2B SaaS,45,https://linear.app,Issue tracker
Vanta,www.vanta.com,B2B SaaS,280,https://vanta.com,Security SaaS
"""
    result = CSVImportService.import_from_csv_content(
        db=db_session,
        campaign_id=test_campaign.id,
        csv_text=csv_data,
    )

    assert result.total_rows == 2
    assert result.accepted == 2
    assert result.rejected == 0
    assert result.duplicates_in_file_skipped == 0
    assert len(result.company_ids) == 2

    # Check companies in DB
    linear = db_session.scalar(select(Company).where(Company.normalized_domain == "linear.app"))
    assert linear is not None
    assert linear.company_name == "Linear"
    assert linear.employee_range == "45"

    vanta = db_session.scalar(select(Company).where(Company.normalized_domain == "vanta.com"))
    assert vanta is not None


def test_import_in_file_deduplication(db_session: Session, test_campaign: Campaign):
    csv_data = """company_name,domain,industry,employee_count
Linear,linear.app,B2B SaaS,45
Linear Pricing,http://linear.app:443/pricing,B2B SaaS,45
Linear Dup,https://www.linear.app,B2B SaaS,45
"""
    result = CSVImportService.import_from_csv_content(
        db=db_session,
        campaign_id=test_campaign.id,
        csv_text=csv_data,
    )

    assert result.total_rows == 3
    assert result.accepted == 1
    assert result.duplicates_in_file_skipped == 2
    assert result.rejected == 0
    assert len(result.company_ids) == 1


def test_import_existing_db_deduplication(db_session: Session, test_campaign: Campaign):
    # Pre-seed company
    existing = Company(
        normalized_domain="attio.com",
        company_name="Attio Pre-existing",
        industry="CRM",
        employee_range="50",
    )
    db_session.add(existing)
    db_session.commit()

    csv_data = """company_name,domain,industry,employee_count
Attio,https://attio.com,CRM,50
Plane,https://plane.so,B2B SaaS,35
"""
    result = CSVImportService.import_from_csv_content(
        db=db_session,
        campaign_id=test_campaign.id,
        csv_text=csv_data,
    )

    assert result.total_rows == 2
    assert result.accepted == 1  # Only Plane is brand new
    assert result.duplicates_existing_associated == 1  # Attio reused
    assert len(result.company_ids) == 2


def test_import_idempotency_on_repeated_upload(db_session: Session, test_campaign: Campaign):
    csv_data = """company_name,domain
Raycast,raycast.com
PostHog,posthog.com
"""
    # First upload
    res1 = CSVImportService.import_from_csv_content(
        db=db_session, campaign_id=test_campaign.id, csv_text=csv_data
    )
    assert res1.accepted == 2

    # Second upload with identical content
    res2 = CSVImportService.import_from_csv_content(
        db=db_session, campaign_id=test_campaign.id, csv_text=csv_data
    )
    assert res2.accepted == 0
    assert res2.duplicates_existing_associated == 2
    assert len(res2.company_ids) == 2

    # Total companies in DB should still be 2
    count = db_session.scalar(
        select(Company).where(Company.normalized_domain.in_(["raycast.com", "posthog.com"]))
    )
    assert count is not None


def test_partial_failure_with_row_errors(db_session: Session, test_campaign: Campaign):
    csv_data = """company_name,domain,employee_count
ValidCo,validco.com,30
BadDomainCo,not-a-valid-domain..com,25
,validco2.com,50
MalformedSize,another-valid.com,not_an_int
"""
    result = CSVImportService.import_from_csv_content(
        db=db_session,
        campaign_id=test_campaign.id,
        csv_text=csv_data,
    )

    assert result.total_rows == 4
    assert result.accepted == 1  # Only ValidCo passes
    assert result.rejected == 3
    assert len(result.row_errors) == 3

    reasons = [err.reason for err in result.row_errors]
    assert any("consecutive dots" in r for r in reasons)
    assert any("Missing company name" in r for r in reasons)
    assert any("must be a non-negative integer" in r for r in reasons)


def test_missing_required_headers(db_session: Session, test_campaign: Campaign):
    bad_csv = "random_header,notes\n123,some notes"
    with pytest.raises(ValidationError, match="Missing required 'domain' column"):
        CSVImportService.import_from_csv_content(
            db=db_session, campaign_id=test_campaign.id, csv_text=bad_csv
        )


def test_import_against_benchmark_dataset(db_session: Session, test_campaign: Campaign):
    with open("sample_data/benchmark_companies.csv", encoding="utf-8") as f:
        content = f.read()

    result = CSVImportService.import_from_csv_content(
        db=db_session,
        campaign_id=test_campaign.id,
        csv_text=content,
    )

    assert result.total_rows == 25
    # 25 total:
    # 4 rejected (not-a-valid-domain..com, ftp://something, missing domain, not_a_number size)
    # 3 in-file duplicates (NormalizeTest1=vanta, NormalizeTest2=linear, DuplicateRow=attio)
    # 18 accepted unique accounts
    assert result.rejected == 4
    assert result.duplicates_in_file_skipped == 3
    assert result.accepted == 18
    assert len(result.company_ids) == 18
