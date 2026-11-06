"""Unit tests for EvidenceService and cryptographic provenance hashing."""

from sqlalchemy.orm import Session

from app.db.models.company import Company
from app.services.evidence import EvidenceService


def test_content_hash_deterministic():
    text = "We provide 24/7 technical customer support."
    h1 = EvidenceService.compute_content_hash(text)
    h2 = EvidenceService.compute_content_hash(text)
    assert h1 == h2
    assert len(h1) == 64  # SHA-256 is 64 hex characters


def test_persist_evidence_and_signal_detection(db_session: Session):
    company = Company(normalized_domain="vanta.com", company_name="Vanta")
    db_session.add(company)
    db_session.commit()

    raw_text = (
        "Vanta automates compliance for B2B SaaS. We provide live customer support and help center."
    )
    evidence = EvidenceService.persist_evidence(
        db=db_session,
        company_id=company.id,
        source_type="mock_provider",
        raw_text=raw_text,
        source_url="https://vanta.com",
    )
    db_session.commit()

    assert evidence.company_id == company.id
    assert evidence.content_hash == EvidenceService.compute_content_hash(raw_text)
    assert "public support/help center" in evidence.field_names_supported
    assert "b2b_saas_model" in evidence.field_names_supported


def test_has_fresh_evidence_check(db_session: Session):
    company = Company(normalized_domain="linear.app", company_name="Linear")
    db_session.add(company)
    db_session.commit()

    # Before evidence is persisted
    assert EvidenceService.has_fresh_evidence(db_session, company.id) is False

    # Persist evidence
    EvidenceService.persist_evidence(
        db=db_session,
        company_id=company.id,
        source_type="mock_provider",
        raw_text="Linear issue tracking software.",
    )
    db_session.commit()

    # Now fresh evidence exists
    assert EvidenceService.has_fresh_evidence(db_session, company.id, max_age_days=30) is True
    # With 0-day max_age, negative window should consider it stale
    assert EvidenceService.has_fresh_evidence(db_session, company.id, max_age_days=-1) is False
