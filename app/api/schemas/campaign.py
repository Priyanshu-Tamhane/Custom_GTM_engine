"""Pydantic schemas for Campaign management."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class CampaignBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255, description="Campaign name")
    product_description: str = Field(
        ..., min_length=5, description="Product value proposition for ICP matching"
    )
    icp_config: dict[str, Any] = Field(
        default_factory=dict, description="Structured ICP criteria (industries, size, signals)"
    )
    rubric_version: str = Field(
        default="v1", max_length=50, description="Version of the qualification rubric"
    )


class CampaignCreate(CampaignBase):
    pass


class CampaignResponse(CampaignBase):
    id: uuid.UUID
    created_at: datetime
    updated_at: datetime
    company_count: int = 0

    model_config = {"from_attributes": True}
