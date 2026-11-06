"""Pydantic schemas for company records, evidence, and enrichment runs."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class SourceEvidenceResponse(BaseModel):
    id: uuid.UUID
    source_type: str
    source_url: str | None = None
    content_hash: str
    excerpt: str
    field_names_supported: list[str] | None = None
    retrieved_at: datetime

    model_config = {"from_attributes": True}


class EnrichmentRunResponse(BaseModel):
    id: uuid.UUID
    provider: str
    status: str
    attempt_count: int
    started_at: datetime
    finished_at: datetime | None = None
    error_type: str | None = None
    error_message: str | None = None

    model_config = {"from_attributes": True}


class CompanyDetailResponse(BaseModel):
    id: uuid.UUID
    normalized_domain: str
    company_name: str
    industry: str | None = None
    employee_range: str | None = None
    description: str | None = None
    record_status: str
    created_at: datetime
    updated_at: datetime
    evidence: list[SourceEvidenceResponse] = Field(default_factory=list)
    recent_runs: list[EnrichmentRunResponse] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class EnrichmentBatchResponse(BaseModel):
    total_companies: int
    succeeded: int
    failed: int
    skipped_fresh: int
    run_ids: list[uuid.UUID] = Field(default_factory=list)
    errors: list[dict[str, Any]] = Field(default_factory=list)
