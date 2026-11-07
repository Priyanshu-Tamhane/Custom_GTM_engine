"""Unit tests for FactExtractorService and evidence citation guardrails."""

import uuid
from datetime import UTC, datetime

import pytest

from app.core.exceptions import EntityNotFoundError
from app.db.models.campaign import Campaign, CampaignCompany
from app.db.models.company import Company
from app.db.models.evidence import SourceEvidence
from app.providers.llm.mock_llm import MockLLMProvider
from app.services.extractor import FactExtractorService


def test_extractor_successful_extraction(db_session):
    """Verify standard extraction populates company attributes and verifies evidence IDs."""
    company = Company(
        normalized_domain="vanta.com",
        company_name="vanta.com",
        record_status="imported",
    )
    db_session.add(company)
    db_session.commit()

    ev_id = uuid.uuid4()
    evidence = SourceEvidence(
        id=ev_id,
        company_id=company.id,
        source_type="website",
        source_url="https://vanta.com",
        retrieved_at=datetime.now(UTC),
        content_hash="abc12345",
        excerpt="Vanta automates compliance for B2B SaaS. Has 200-300 employees and live support desk.",
    )
    db_session.add(evidence)
    db_session.commit()

    llm = MockLLMProvider(default_scenario="success")
    service = FactExtractorService(db=db_session, llm_provider=llm)

    result = service.extract_company_facts(company_id=company.id)

    assert result.company_id == company.id
    assert result.extracted_facts.company_name == "Vanta"
    assert result.extracted_facts.industry.value == "B2B SaaS"
    assert result.extracted_facts.employee_range.value == "200-300"
    assert len(result.extracted_facts.relevant_signals) == 2
    assert result.extracted_facts.needs_human_review is False
    assert len(result.unverified_evidence_ids) == 0

    # Verify company updated in DB
    db_session.refresh(company)
    assert company.company_name == "Vanta"
    assert company.industry == "B2B SaaS"
    assert company.employee_range == "200-300"
    assert company.record_status == "facts_extracted"


def test_extractor_hallucinated_evidence_id_guardrail(db_session):
    """Guardrail test: invent an evidence ID, verify it is caught, stripped, and flagged for review."""
    company = Company(
        normalized_domain="hallucinating.com",
        company_name="Hallucinating Co",
        record_status="imported",
    )
    db_session.add(company)
    db_session.commit()

    real_ev_id = uuid.uuid4()
    evidence = SourceEvidence(
        id=real_ev_id,
        company_id=company.id,
        source_type="website",
        source_url="https://hallucinating.com",
        retrieved_at=datetime.now(UTC),
        content_hash="hash987",
        excerpt="Real evidence excerpt here.",
    )
    db_session.add(evidence)
    db_session.commit()

    # Configure mock to output hallucinated ID: 99999999-9999-9999-9999-999999999999
    llm = MockLLMProvider(default_scenario="hallucinated_id")
    service = FactExtractorService(db=db_session, llm_provider=llm)

    result = service.extract_company_facts(company_id=company.id)

    # Guardrail assertions
    assert result.extracted_facts.needs_human_review is True
    assert "Hallucinated" in result.extracted_facts.reason_for_review or "hallucinated" in result.extracted_facts.reason_for_review
    assert "99999999-9999-9999-9999-999999999999" in result.unverified_evidence_ids
    # The hallucinated ID was stripped from the field
    assert "99999999-9999-9999-9999-999999999999" not in result.extracted_facts.industry.evidence_ids


def test_extractor_malformed_json_fallback(db_session):
    """Verify invalid JSON from model is caught gracefully without throwing 500 error."""
    company = Company(
        normalized_domain="corrupted.com",
        company_name="Corrupted Co",
        record_status="imported",
    )
    db_session.add(company)
    db_session.commit()

    evidence = SourceEvidence(
        company_id=company.id,
        source_type="website",
        source_url="https://corrupted.com",
        retrieved_at=datetime.now(UTC),
        content_hash="hashcorrupted",
        excerpt="Some website text.",
    )
    db_session.add(evidence)
    db_session.commit()

    llm = MockLLMProvider(default_scenario="invalid_json")
    service = FactExtractorService(db=db_session, llm_provider=llm)

    result = service.extract_company_facts(company_id=company.id)

    assert result.extracted_facts.needs_human_review is True
    assert "malformed JSON" in result.extracted_facts.reason_for_review


def test_extractor_schema_validation_failure_missing_fields(db_session):
    """Verify that model output missing required schema fields triggers human review."""
    company = Company(
        normalized_domain="missingfields.com",
        company_name="Missing Co",
        record_status="imported",
    )
    db_session.add(company)
    db_session.commit()

    evidence = SourceEvidence(
        company_id=company.id,
        source_type="website",
        source_url="https://missingfields.com",
        retrieved_at=datetime.now(UTC),
        content_hash="hash_missing",
        excerpt="Missing fields text.",
    )
    db_session.add(evidence)
    db_session.commit()

    # Create mock LLM returning incomplete dictionary
    class IncompleteLLM(MockLLMProvider):
        def generate_structured_json(self, system_prompt: str, user_prompt: str):
            from app.providers.llm.base import LLMResponse
            return LLMResponse(
                raw_json='{"company_name": "Incomplete"}',  # Missing description, industry, etc.
                model_name="mock-incomplete",
            )

    service = FactExtractorService(db=db_session, llm_provider=IncompleteLLM())
    result = service.extract_company_facts(company_id=company.id)

    assert result.extracted_facts.needs_human_review is True
    assert "Extraction violated schema" in result.extracted_facts.reason_for_review


def test_extractor_schema_validation_failure_invalid_type(db_session):
    """Verify that model output with invalid types (e.g. non-numeric confidence) triggers human review."""
    company = Company(
        normalized_domain="invalidtype.com",
        company_name="Invalid Type Co",
        record_status="imported",
    )
    db_session.add(company)
    db_session.commit()

    evidence = SourceEvidence(
        company_id=company.id,
        source_type="website",
        source_url="https://invalidtype.com",
        retrieved_at=datetime.now(UTC),
        content_hash="hash_invalid",
        excerpt="Invalid type text.",
    )
    db_session.add(evidence)
    db_session.commit()

    # Create mock LLM returning string instead of float for confidence
    class InvalidTypeLLM(MockLLMProvider):
        def generate_structured_json(self, system_prompt: str, user_prompt: str):
            from app.providers.llm.base import LLMResponse
            return LLMResponse(
                raw_json='''{
                    "company_name": "Invalid Co",
                    "description": "Factual description",
                    "industry": {"value": "SaaS", "confidence": "very_high", "evidence_ids": []},
                    "employee_range": {"value": "50", "confidence": 0.8, "evidence_ids": []}
                }''',
                model_name="mock-invalid-type",
            )

    service = FactExtractorService(db=db_session, llm_provider=InvalidTypeLLM())
    result = service.extract_company_facts(company_id=company.id)

    assert result.extracted_facts.needs_human_review is True
    assert "Extraction violated schema" in result.extracted_facts.reason_for_review


def test_extractor_no_evidence_available(db_session):
    """Verify extraction handles account with no evidence by marking unknown and requiring review."""
    company = Company(
        normalized_domain="noevidence.org",
        company_name="No Evidence Org",
        record_status="imported",
    )
    db_session.add(company)
    db_session.commit()

    llm = MockLLMProvider()
    service = FactExtractorService(db=db_session, llm_provider=llm)

    result = service.extract_company_facts(company_id=company.id)

    assert result.extracted_facts.needs_human_review is True
    assert "No source evidence" in result.extracted_facts.reason_for_review
    assert "industry" in result.extracted_facts.unknown_fields
    assert result.extracted_facts.industry.value is None


def test_extractor_nonexistent_company_raises(db_session):
    """Verify EntityNotFoundError raised when company does not exist."""
    service = FactExtractorService(db=db_session, llm_provider=MockLLMProvider())

    with pytest.raises(EntityNotFoundError):
        service.extract_company_facts(company_id=uuid.uuid4())


def test_extractor_campaign_companies_batch(db_session):
    """Verify batch campaign extraction processes all linked accounts."""
    campaign = Campaign(
        name="Batch Test Campaign",
        product_description="Test Product for Support automation",
        icp_config={"industries": ["B2B SaaS"]},
    )
    db_session.add(campaign)
    db_session.commit()

    # Add 2 companies
    c1 = Company(normalized_domain="comp1.com", company_name="comp1.com")
    c2 = Company(normalized_domain="comp2.com", company_name="comp2.com")
    db_session.add_all([c1, c2])
    db_session.commit()

    # Link both to campaign
    db_session.add_all([
        CampaignCompany(campaign_id=campaign.id, company_id=c1.id),
        CampaignCompany(campaign_id=campaign.id, company_id=c2.id),
    ])
    # Add evidence for c1
    db_session.add(
        SourceEvidence(
            company_id=c1.id,
            source_type="website",
            content_hash="hash1",
            excerpt="comp1 B2B SaaS platform.",
        )
    )
    db_session.commit()

    service = FactExtractorService(db=db_session, llm_provider=MockLLMProvider())
    results = service.extract_campaign_companies(campaign_id=campaign.id)

    assert len(results) == 2
    comp_ids = {r.company_id for r in results}
    assert c1.id in comp_ids
    assert c2.id in comp_ids
