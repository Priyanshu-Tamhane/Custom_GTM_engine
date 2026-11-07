"""Pydantic schemas for structured LLM fact extraction and verification."""

import uuid

from pydantic import BaseModel, Field


class ExtractedField(BaseModel):
    """A single extracted factual field with confidence and source citations."""

    value: str | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    evidence_ids: list[str] = Field(default_factory=list)


class ExtractedSignal(BaseModel):
    """A detected buying/timing signal backed by source evidence."""

    signal: str
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    evidence_ids: list[str] = Field(default_factory=list)


class CompanyFactExtraction(BaseModel):
    """Strict structured extraction output expected from the LLM."""

    company_name: str
    description: str = Field(..., description="Concise, factual summary of the business")
    industry: ExtractedField
    employee_range: ExtractedField
    relevant_signals: list[ExtractedSignal] = Field(default_factory=list)
    unknown_fields: list[str] = Field(
        default_factory=list, description="Attributes that could not be determined from evidence"
    )
    needs_human_review: bool = False
    reason_for_review: str | None = None


class ExtractionResultResponse(BaseModel):
    """API response for a completed company fact extraction."""

    company_id: uuid.UUID
    extracted_facts: CompanyFactExtraction
    model_name: str
    input_tokens: int = 0
    output_tokens: int = 0
    estimated_cost_usd: float = 0.0
    latency_ms: float = 0.0
    unverified_evidence_ids: list[str] = Field(
        default_factory=list, description="Any evidence IDs hallucinated by the model"
    )
