"""Unit tests for EnrichmentOrchestrator, bounded retries, and partial failure isolation."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.company import Company
from app.db.models.evidence import SourceEvidence
from app.providers.mock_provider import MockEnrichmentProvider
from app.services.enrichment_orchestrator import EnrichmentOrchestrator


def test_enrich_company_success(db_session: Session):
    company = Company(normalized_domain="incident.io", company_name="IncidentIO")
    db_session.add(company)
    db_session.commit()

    provider = MockEnrichmentProvider()
    orchestrator = EnrichmentOrchestrator(provider=provider, max_retries=3, backoff_factor=0.001)

    run = orchestrator.enrich_company(db_session, company)

    assert run.status == "succeeded"
    assert run.attempt_count == 1
    assert company.record_status == "enriched"
    assert company.description is not None

    # Check evidence was persisted
    evidence = db_session.scalar(
        select(SourceEvidence).where(SourceEvidence.company_id == company.id)
    )
    assert evidence is not None
    assert "24/7 dedicated customer support" in evidence.excerpt


def test_enrich_company_flaky_retry_succeeds(db_session: Session):
    company = Company(normalized_domain="flakyco.com", company_name="FlakyCo")
    db_session.add(company)
    db_session.commit()

    provider = MockEnrichmentProvider()
    provider.set_domain_scenario("flakyco.com", "flaky")
    provider.flaky_success_threshold = 2

    orchestrator = EnrichmentOrchestrator(provider=provider, max_retries=3, backoff_factor=0.001)

    run = orchestrator.enrich_company(db_session, company)

    # Should succeed on attempt 2
    assert run.status == "succeeded"
    assert run.attempt_count == 2
    assert company.record_status == "enriched"


def test_enrich_company_permanent_failure_no_retries(db_session: Session):
    company = Company(normalized_domain="deadco.xyz", company_name="DeadCo")
    db_session.add(company)
    db_session.commit()

    provider = MockEnrichmentProvider(default_scenario="not_found")
    orchestrator = EnrichmentOrchestrator(provider=provider, max_retries=3, backoff_factor=0.001)

    run = orchestrator.enrich_company(db_session, company)

    # Permanent failure should not retry
    assert run.status == "permanent_failed"
    assert run.attempt_count == 1
    assert run.error_type == "HTTP_404_NotFound"
    assert company.record_status == "enrichment_failed"


def test_enrich_company_max_retries_exhausted(db_session: Session):
    company = Company(normalized_domain="downserver.com", company_name="DownServer")
    db_session.add(company)
    db_session.commit()

    provider = MockEnrichmentProvider(default_scenario="timeout")
    orchestrator = EnrichmentOrchestrator(provider=provider, max_retries=3, backoff_factor=0.001)

    run = orchestrator.enrich_company(db_session, company)

    assert run.status == "retryable_failed"
    assert run.attempt_count == 3
    assert company.record_status == "enrichment_failed"


def test_enrich_company_skips_when_fresh_evidence_exists(db_session: Session):
    company = Company(normalized_domain="vanta.com", company_name="Vanta")
    db_session.add(company)
    db_session.commit()

    provider = MockEnrichmentProvider()
    orchestrator = EnrichmentOrchestrator(provider=provider, max_retries=3, backoff_factor=0.001)

    # Run 1: Fetches and persists evidence
    run1 = orchestrator.enrich_company(db_session, company)
    assert run1.attempt_count == 1

    # Run 2: Fresh evidence exists, skips fetch
    run2 = orchestrator.enrich_company(db_session, company, force_refresh=False)
    assert run2.attempt_count == 0
    assert run2.status == "succeeded"


def test_enrich_batch_partial_failure_isolation(db_session: Session):
    c1 = Company(normalized_domain="goodco.com", company_name="GoodCo")
    c2 = Company(normalized_domain="notfound.com", company_name="NotFoundCo")
    c3 = Company(normalized_domain="timeout.com", company_name="TimeoutCo")
    db_session.add_all([c1, c2, c3])
    db_session.commit()

    provider = MockEnrichmentProvider(default_scenario="success")
    provider.set_domain_scenario("notfound.com", "not_found")
    provider.set_domain_scenario("timeout.com", "timeout")

    orchestrator = EnrichmentOrchestrator(provider=provider, max_retries=2, backoff_factor=0.001)

    summary = orchestrator.enrich_batch(db_session, [c1, c2, c3])

    assert summary.total_companies == 3
    assert summary.succeeded == 1
    assert summary.failed == 2
    assert len(summary.errors) == 2

    # Verify c1 succeeded and has evidence despite c2 and c3 failing
    assert c1.record_status == "enriched"
    assert c2.record_status == "enrichment_failed"
    assert c3.record_status == "enrichment_failed"
