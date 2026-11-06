"""Evidence persistence, provenance hashing, and freshness checking service."""

import hashlib
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.evidence import SourceEvidence


class EvidenceService:
    """Manages immutable source evidence records and provenance integrity."""

    @staticmethod
    def compute_content_hash(content: str) -> str:
        """Compute SHA-256 cryptographic hash of raw evidence payload."""
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    @classmethod
    def has_fresh_evidence(
        cls,
        db: Session,
        company_id: uuid.UUID,
        max_age_days: int = 30,
    ) -> bool:
        """Check if unexpired evidence already exists for the company.

        Args:
            db: Active database session.
            company_id: Target company UUID.
            max_age_days: Number of days before evidence is considered stale.

        Returns:
            True if recent evidence exists, False otherwise.
        """
        cutoff = datetime.now(UTC) - timedelta(days=max_age_days)
        recent_evidence = db.scalar(
            select(SourceEvidence)
            .where(
                SourceEvidence.company_id == company_id,
                SourceEvidence.retrieved_at >= cutoff,
            )
            .limit(1)
        )
        return recent_evidence is not None

    @classmethod
    def persist_evidence(
        cls,
        db: Session,
        company_id: uuid.UUID,
        source_type: str,
        raw_text: str,
        source_url: str | None = None,
        source_reference: str | None = None,
        field_names_supported: list[str] | None = None,
        metadata_json: dict | None = None,
    ) -> SourceEvidence:
        """Persist verifiable evidence excerpt with timestamp and SHA-256 integrity hash.

        Args:
            db: Active database session.
            company_id: Target company UUID.
            source_type: Provider category (e.g. 'website', 'public_api').
            raw_text: Raw retrieved text content.
            source_url: Source URL fetched.
            source_reference: Source API ID or record reference.
            field_names_supported: List of fields this snippet provides evidence for.
            metadata_json: Optional provider metadata.

        Returns:
            Newly created SourceEvidence instance.
        """
        content_hash = cls.compute_content_hash(raw_text)

        # Detect relevant signals in text
        signals: list[str] = list(field_names_supported or [])
        lower_text = raw_text.lower()
        if (
            any(k in lower_text for k in ("support", "help center", "customer service"))
            and "public support/help center" not in signals
        ):
            signals.append("public support/help center")
        if (
            any(k in lower_text for k in ("b2b", "saas", "enterprise software"))
            and "b2b_saas_model" not in signals
        ):
            signals.append("b2b_saas_model")

        evidence = SourceEvidence(
            company_id=company_id,
            source_type=source_type,
            source_url=source_url,
            source_reference=source_reference,
            content_hash=content_hash,
            excerpt=raw_text[:1500].strip(),  # Store focused excerpt
            field_names_supported=signals or None,
            metadata_json=metadata_json,
            retrieved_at=datetime.now(UTC),
        )

        db.add(evidence)
        db.flush()
        return evidence
