"""Pydantic schemas for CSV imports and row-level validation reports."""

import uuid

from pydantic import BaseModel, Field


class RowError(BaseModel):
    row_number: int = Field(..., description="1-indexed row number in the CSV file")
    raw_domain: str | None = Field(None, description="Raw domain input from the row")
    raw_company_name: str | None = Field(None, description="Raw company name input")
    reason: str = Field(..., description="Explanation of why this row was rejected")


class ImportSummaryResponse(BaseModel):
    campaign_id: uuid.UUID
    source_import_id: str | None = None
    total_rows: int = Field(..., description="Total rows parsed in file")
    accepted: int = Field(..., description="Rows successfully imported or attached")
    duplicates_in_file_skipped: int = Field(
        ..., description="Duplicate rows inside the same file that were skipped"
    )
    duplicates_existing_associated: int = Field(
        ..., description="Existing companies in DB attached to this campaign"
    )
    rejected: int = Field(..., description="Rows rejected due to validation errors")
    company_ids: list[uuid.UUID] = Field(
        default_factory=list, description="IDs of all companies attached to this campaign"
    )
    row_errors: list[RowError] = Field(
        default_factory=list, description="Detailed row-level rejection reasons"
    )
