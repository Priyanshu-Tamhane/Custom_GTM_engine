"""Integration tests for Campaign and CSV Import API route handlers."""

import io
import uuid

import pytest
from fastapi import UploadFile
from sqlalchemy.orm import Session

from app.api.routes.campaigns import (
    create_campaign,
    get_campaign,
    import_companies_csv,
    list_campaigns,
)
from app.api.schemas.campaign import CampaignCreate
from app.core.exceptions import EntityNotFoundError, ValidationError


def test_create_and_get_campaign(db_session: Session):
    payload = CampaignCreate(
        name="Integration Test Campaign",
        product_description="AI-Powered SDR triage bot",
        icp_config={
            "target_industries": ["B2B SaaS"],
            "employee_range": [20, 300],
        },
        rubric_version="v1",
    )
    created = create_campaign(payload=payload, db=db_session)
    assert created.name == payload.name
    assert created.id is not None
    assert created.company_count == 0

    fetched = get_campaign(campaign_id=created.id, db=db_session)
    assert fetched.id == created.id
    assert fetched.name == payload.name


def test_list_campaigns(db_session: Session):
    c1 = CampaignCreate(name="Camp 1", product_description="Desc 1")
    c2 = CampaignCreate(name="Camp 2", product_description="Desc 2")
    create_campaign(payload=c1, db=db_session)
    create_campaign(payload=c2, db=db_session)

    campaigns = list_campaigns(skip=0, limit=10, db=db_session)
    assert len(campaigns) >= 2


def test_upload_csv_import_route(db_session: Session):
    c = CampaignCreate(name="Import Campaign", product_description="AI Support Product Description")
    camp = create_campaign(payload=c, db=db_session)

    csv_content = b"""company_name,domain,industry,employee_count
Linear,linear.app,B2B SaaS,45
Vanta,vanta.com,B2B SaaS,280
BadRow,,invalid..com,
"""
    file = UploadFile(
        filename="companies.csv",
        file=io.BytesIO(csv_content),
        headers={"content-type": "text/csv"},
    )

    summary = import_companies_csv(
        campaign_id=camp.id,
        file=file,
        db=db_session,
    )

    assert summary.campaign_id == camp.id
    assert summary.total_rows == 3
    assert summary.accepted == 2
    assert summary.rejected == 1
    assert len(summary.row_errors) == 1

    # Verify updated company count
    updated_camp = get_campaign(campaign_id=camp.id, db=db_session)
    assert updated_camp.company_count == 2


def test_import_nonexistent_campaign_raises_404(db_session: Session):
    fake_id = uuid.uuid4()
    file = UploadFile(
        filename="test.csv",
        file=io.BytesIO(b"company_name,domain\nAcme,acme.com\n"),
    )
    with pytest.raises(EntityNotFoundError, match="not found"):
        import_companies_csv(
            campaign_id=fake_id,
            file=file,
            db=db_session,
        )


def test_import_invalid_file_extension_raises_validation_error(db_session: Session):
    c = CampaignCreate(
        name="Bad Ext Campaign", product_description="AI Support Product Description"
    )
    camp = create_campaign(payload=c, db=db_session)

    file = UploadFile(
        filename="data.txt",
        file=io.BytesIO(b"dummy data"),
    )
    with pytest.raises(ValidationError, match="must be a .csv file"):
        import_companies_csv(
            campaign_id=camp.id,
            file=file,
            db=db_session,
        )


def test_import_missing_file_raises_validation_error(db_session: Session):
    c = CampaignCreate(
        name="No File Campaign", product_description="AI Support Product Description"
    )
    camp = create_campaign(payload=c, db=db_session)

    with pytest.raises(ValidationError, match="No CSV file provided"):
        import_companies_csv(
            campaign_id=camp.id,
            file=None,
            db=db_session,
        )
