"""API routes for campaign creation and CSV company imports."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.schemas.campaign import CampaignCreate, CampaignResponse
from app.api.schemas.import_job import ImportSummaryResponse
from app.core.exceptions import EntityNotFoundError, ValidationError
from app.db.models.campaign import Campaign, CampaignCompany
from app.db.session import get_sync_db_session

router = APIRouter(prefix="/campaigns", tags=["Campaigns & Imports"])


@router.post("", response_model=CampaignResponse, status_code=status.HTTP_201_CREATED)
def create_campaign(
    payload: CampaignCreate,
    db: Annotated[Session, Depends(get_sync_db_session)],
) -> CampaignResponse:
    """Create a new GTM campaign experiment with target ICP criteria."""
    campaign = Campaign(
        name=payload.name,
        product_description=payload.product_description,
        icp_config=payload.icp_config,
        rubric_version=payload.rubric_version,
    )
    db.add(campaign)
    db.commit()
    db.refresh(campaign)

    return CampaignResponse(
        id=campaign.id,
        name=campaign.name,
        product_description=campaign.product_description,
        icp_config=campaign.icp_config,
        rubric_version=campaign.rubric_version,
        created_at=campaign.created_at,
        updated_at=campaign.updated_at,
        company_count=0,
    )


@router.get("/{campaign_id}", response_model=CampaignResponse)
def get_campaign(
    campaign_id: uuid.UUID,
    db: Annotated[Session, Depends(get_sync_db_session)],
) -> CampaignResponse:
    """Fetch campaign details along with total associated companies."""
    campaign = db.scalar(select(Campaign).where(Campaign.id == campaign_id))
    if not campaign:
        raise EntityNotFoundError(f"Campaign with ID {campaign_id} not found")

    count = (
        db.scalar(
            select(func.count(CampaignCompany.id)).where(CampaignCompany.campaign_id == campaign_id)
        )
        or 0
    )

    return CampaignResponse(
        id=campaign.id,
        name=campaign.name,
        product_description=campaign.product_description,
        icp_config=campaign.icp_config,
        rubric_version=campaign.rubric_version,
        created_at=campaign.created_at,
        updated_at=campaign.updated_at,
        company_count=count,
    )


@router.get("", response_model=list[CampaignResponse])
def list_campaigns(
    db: Annotated[Session, Depends(get_sync_db_session)],
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[CampaignResponse]:
    """List all campaigns with pagination."""
    campaigns = db.scalars(select(Campaign).offset(skip).limit(limit)).all()
    results: list[CampaignResponse] = []

    for c in campaigns:
        count = (
            db.scalar(
                select(func.count(CampaignCompany.id)).where(CampaignCompany.campaign_id == c.id)
            )
            or 0
        )
        results.append(
            CampaignResponse(
                id=c.id,
                name=c.name,
                product_description=c.product_description,
                icp_config=c.icp_config,
                rubric_version=c.rubric_version,
                created_at=c.created_at,
                updated_at=c.updated_at,
                company_count=count,
            )
        )

    return results


@router.post(
    "/{campaign_id}/imports",
    response_model=ImportSummaryResponse,
    status_code=status.HTTP_200_OK,
)
def import_companies_csv(
    campaign_id: uuid.UUID,
    db: Annotated[Session, Depends(get_sync_db_session)],
    file: Annotated[UploadFile | None, File()] = None,
    source_import_id: Annotated[str | None, Form()] = None,
) -> ImportSummaryResponse:
    """Upload and process a CSV file of company records for a campaign.

    Validates columns, normalizes domains, deduplicates records,
    and returns an auditable row-level summary report.
    """
    if file is None:
        raise ValidationError("No CSV file provided in upload")

    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise ValidationError("Uploaded file must be a .csv file")

    content_bytes = file.file.read()
    try:
        csv_text = content_bytes.decode("utf-8")
    except UnicodeDecodeError:
        try:
            csv_text = content_bytes.decode("latin-1")
        except Exception as exc:
            raise ValidationError(f"Invalid file encoding: {exc}") from exc

    from app.services.importer import CSVImportService

    return CSVImportService.import_from_csv_content(
        db=db,
        campaign_id=campaign_id,
        csv_text=csv_text,
        source_import_id=source_import_id,
    )
