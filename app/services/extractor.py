"""Fact extraction service enforcing evidence verification guardrails and schema compliance."""

import json
import uuid
from collections.abc import Sequence

from pydantic import ValidationError as PydanticValidationError
from sqlalchemy.orm import Session

from app.api.schemas.extraction import (
    CompanyFactExtraction,
    ExtractedField,
    ExtractionResultResponse,
)
from app.core.config import get_settings
from app.core.exceptions import EntityNotFoundError
from app.core.logging import get_logger
from app.db.models.campaign import Campaign, CampaignCompany
from app.db.models.company import Company
from app.db.models.evidence import SourceEvidence
from app.providers.llm.base import BaseLLMProvider
from app.providers.llm.groq_llm import GroqLLMProvider
from app.providers.llm.mock_llm import MockLLMProvider
from app.services.prompts import build_extraction_prompts

logger = get_logger("fact_extractor_service")


class FactExtractorService:
    """Orchestrates structured LLM fact extraction with evidence verification guardrails."""

    def __init__(self, db: Session, llm_provider: BaseLLMProvider | None = None):
        self.db = db
        if llm_provider is not None:
            self.llm_provider = llm_provider
        else:
            settings = get_settings()
            if settings.LLM_PROVIDER.lower() == "groq" and settings.GROQ_API_KEY:
                self.llm_provider = GroqLLMProvider()
            else:
                self.llm_provider = MockLLMProvider()

    def _verify_and_sanitize_evidence_citations(
        self,
        extracted: CompanyFactExtraction,
        valid_evidence_ids: set[str],
    ) -> list[str]:
        """Guardrail: Detect, record, and strip any hallucinated or unverified evidence citations.

        Args:
            extracted: Pydantic model returned from LLM output.
            valid_evidence_ids: Set of actual evidence IDs present in the DB for this company.

        Returns:
            List of unverified / hallucinated evidence ID strings detected.
        """
        unverified_ids: list[str] = []

        # 1. Verify industry citation
        sanitized_industry_ids: list[str] = []
        for ev_id in extracted.industry.evidence_ids:
            ev_str = str(ev_id).lower()
            if ev_str in valid_evidence_ids:
                sanitized_industry_ids.append(ev_str)
            else:
                unverified_ids.append(ev_str)
        extracted.industry.evidence_ids = sanitized_industry_ids

        # 2. Verify employee range citation
        sanitized_emp_ids: list[str] = []
        for ev_id in extracted.employee_range.evidence_ids:
            ev_str = str(ev_id).lower()
            if ev_str in valid_evidence_ids:
                sanitized_emp_ids.append(ev_str)
            else:
                unverified_ids.append(ev_str)
        extracted.employee_range.evidence_ids = sanitized_emp_ids

        # 3. Verify relevant signals citations
        for sig in extracted.relevant_signals:
            sanitized_sig_ids: list[str] = []
            for ev_id in sig.evidence_ids:
                ev_str = str(ev_id).lower()
                if ev_str in valid_evidence_ids:
                    sanitized_sig_ids.append(ev_str)
                else:
                    unverified_ids.append(ev_str)
            sig.evidence_ids = sanitized_sig_ids

        # If any hallucinated citations were caught, flag for mandatory human review
        if unverified_ids:
            extracted.needs_human_review = True
            hallucination_note = (
                f"Model hallucinated unverified evidence IDs: {', '.join(unverified_ids)}"
            )
            if extracted.reason_for_review:
                extracted.reason_for_review += f"; {hallucination_note}"
            else:
                extracted.reason_for_review = hallucination_note

        return unverified_ids

    def extract_company_facts(self, company_id: uuid.UUID) -> ExtractionResultResponse:
        """Extract verified facts for a single company using LLM with evidence verification.

        Args:
            company_id: UUID of the company account.

        Returns:
            ExtractionResultResponse with verified facts, audit metrics, and review flags.
        """
        company = self.db.query(Company).filter(Company.id == company_id).first()
        if not company:
            raise EntityNotFoundError(f"Company {company_id} not found")

        evidence_list: Sequence[SourceEvidence] = (
            self.db.query(SourceEvidence)
            .filter(SourceEvidence.company_id == company_id)
            .order_by(SourceEvidence.retrieved_at.desc())
            .all()
        )

        valid_evidence_ids = {str(ev.id).lower() for ev in evidence_list}

        # Case 1: No evidence exists yet
        if not evidence_list:
            logger.warning(f"No source evidence found for company {company_id}")
            fallback_facts = CompanyFactExtraction(
                company_name=company.company_name or company.normalized_domain,
                description=company.description or "No evidence available to determine description.",
                industry=ExtractedField(value=None, confidence=0.0, evidence_ids=[]),
                employee_range=ExtractedField(value=None, confidence=0.0, evidence_ids=[]),
                relevant_signals=[],
                unknown_fields=["industry", "employee_range", "signals", "description"],
                needs_human_review=True,
                reason_for_review="No source evidence records found for account.",
            )
            return ExtractionResultResponse(
                company_id=company.id,
                extracted_facts=fallback_facts,
                model_name=self.llm_provider.model_name,
                input_tokens=0,
                output_tokens=0,
                estimated_cost_usd=0.0,
                latency_ms=0.0,
                unverified_evidence_ids=[],
            )

        # Build prompt and execute inference
        system_prompt, user_prompt = build_extraction_prompts(
            domain=company.normalized_domain,
            company_name=company.company_name,
            evidence_list=evidence_list,
        )

        llm_response = self.llm_provider.generate_structured_json(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )

        # Parse JSON
        try:
            raw_data = json.loads(llm_response.raw_json)
        except json.JSONDecodeError as json_err:
            logger.error(f"LLM returned malformed JSON: {json_err}")
            fallback_facts = CompanyFactExtraction(
                company_name=company.company_name,
                description="Failed to parse LLM JSON output.",
                industry=ExtractedField(value=None, confidence=0.0, evidence_ids=[]),
                employee_range=ExtractedField(value=None, confidence=0.0, evidence_ids=[]),
                unknown_fields=["industry", "employee_range", "signals"],
                needs_human_review=True,
                reason_for_review=f"LLM returned malformed JSON: {json_err}",
            )
            return ExtractionResultResponse(
                company_id=company.id,
                extracted_facts=fallback_facts,
                model_name=llm_response.model_name,
                input_tokens=llm_response.input_tokens,
                output_tokens=llm_response.output_tokens,
                estimated_cost_usd=llm_response.estimated_cost_usd,
                latency_ms=llm_response.latency_ms,
                unverified_evidence_ids=[],
            )

        # Validate with strict schema
        try:
            extracted_facts = CompanyFactExtraction.model_validate(raw_data)
        except PydanticValidationError as val_err:
            logger.warning(f"LLM output violated Pydantic schema: {val_err}")
            fallback_facts = CompanyFactExtraction(
                company_name=str(raw_data.get("company_name", company.company_name)),
                description=str(raw_data.get("description", "Schema validation failure.")),
                industry=ExtractedField(value=None, confidence=0.0, evidence_ids=[]),
                employee_range=ExtractedField(value=None, confidence=0.0, evidence_ids=[]),
                unknown_fields=["validation_failed"],
                needs_human_review=True,
                reason_for_review=f"Extraction violated schema: {val_err}",
            )
            return ExtractionResultResponse(
                company_id=company.id,
                extracted_facts=fallback_facts,
                model_name=llm_response.model_name,
                input_tokens=llm_response.input_tokens,
                output_tokens=llm_response.output_tokens,
                estimated_cost_usd=llm_response.estimated_cost_usd,
                latency_ms=llm_response.latency_ms,
                unverified_evidence_ids=[],
            )

        # Guardrail: Check and filter evidence citations
        unverified_ids = self._verify_and_sanitize_evidence_citations(
            extracted=extracted_facts,
            valid_evidence_ids=valid_evidence_ids,
        )

        # Update company record in database
        if extracted_facts.description and extracted_facts.description != "N/A":
            company.description = extracted_facts.description

        if extracted_facts.industry.value and extracted_facts.industry.confidence >= 0.5:
            company.industry = extracted_facts.industry.value

        if extracted_facts.employee_range.value and extracted_facts.employee_range.confidence >= 0.5:
            company.employee_range = extracted_facts.employee_range.value

        if (
            company.company_name == company.normalized_domain
            and extracted_facts.company_name
            and extracted_facts.company_name != company.normalized_domain
        ):
            company.company_name = extracted_facts.company_name

        company.record_status = "review_ready" if extracted_facts.needs_human_review else "facts_extracted"
        self.db.commit()
        self.db.refresh(company)

        logger.info(
            f"Company facts extracted company_id={company.id} domain={company.normalized_domain} "
            f"needs_review={extracted_facts.needs_human_review} unverified_citations={len(unverified_ids)}"
        )

        return ExtractionResultResponse(
            company_id=company.id,
            extracted_facts=extracted_facts,
            model_name=llm_response.model_name,
            input_tokens=llm_response.input_tokens,
            output_tokens=llm_response.output_tokens,
            estimated_cost_usd=llm_response.estimated_cost_usd,
            latency_ms=llm_response.latency_ms,
            unverified_evidence_ids=unverified_ids,
        )

    def extract_campaign_companies(
        self, campaign_id: uuid.UUID
    ) -> list[ExtractionResultResponse]:
        """Run batch fact extraction for all companies in a campaign with failure isolation.

        Args:
            campaign_id: UUID of the target campaign.

        Returns:
            List of ExtractionResultResponse for all processed accounts.
        """
        campaign = self.db.query(Campaign).filter(Campaign.id == campaign_id).first()
        if not campaign:
            raise EntityNotFoundError(f"Campaign {campaign_id} not found")

        company_links = (
            self.db.query(CampaignCompany)
            .filter(CampaignCompany.campaign_id == campaign_id)
            .all()
        )

        results: list[ExtractionResultResponse] = []
        for link in company_links:
            try:
                res = self.extract_company_facts(link.company_id)
                results.append(res)
            except Exception as e:  # noqa: BLE001
                logger.error(
                    f"Extraction failed for campaign {campaign_id} company {link.company_id}: {e}"
                )
                # Continue with remaining companies in campaign batch

        return results
