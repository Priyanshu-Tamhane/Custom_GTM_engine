"""Enrichment orchestrator with bounded exponential retries and partial failure isolation."""

import random
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.core.logging import logger
from app.db.models.company import Company
from app.db.models.enrichment import EnrichmentRun
from app.providers.base import BaseEnrichmentProvider, ProviderResult
from app.services.evidence import EvidenceService


@dataclass
class EnrichmentBatchSummary:
    """Summary of a batch enrichment operation."""

    total_companies: int
    succeeded: int = 0
    failed: int = 0
    skipped_fresh: int = 0
    run_ids: list[uuid.UUID] = field(default_factory=list)
    errors: list[dict] = field(default_factory=list)


class EnrichmentOrchestrator:
    """Coordinates company data collection, retries, and evidence persistence."""

    def __init__(
        self,
        provider: BaseEnrichmentProvider,
        max_retries: int = 3,
        backoff_factor: float = 0.5,
        max_backoff_seconds: float = 5.0,
    ):
        self.provider = provider
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor
        self.max_backoff_seconds = max_backoff_seconds

    def _calculate_backoff(self, attempt: int, retry_after: float | None = None) -> float:
        """Calculate exponential backoff with jitter or honour Retry-After."""
        if retry_after is not None and retry_after > 0:
            return min(retry_after, self.max_backoff_seconds)
        delay = self.backoff_factor * (2 ** (attempt - 1))
        jitter = random.uniform(0, 0.1 * delay)
        return min(delay + jitter, self.max_backoff_seconds)

    def enrich_company(
        self,
        db: Session,
        company: Company,
        force_refresh: bool = False,
    ) -> EnrichmentRun:
        """Enrich a single company record with bounded retries and status tracking.

        Args:
            db: Active database session.
            company: Company model instance to enrich.
            force_refresh: If True, bypass fresh evidence cache check.

        Returns:
            The finished EnrichmentRun record.
        """
        # 1. Fresh evidence check
        if not force_refresh and EvidenceService.has_fresh_evidence(db, company.id):
            logger.info(
                f"Skipping enrichment for {company.normalized_domain}: fresh evidence already exists.",
                extra_fields={"company_id": str(company.id)},
            )
            # Create a skipped run record for audit
            run = EnrichmentRun(
                company_id=company.id,
                provider=self.provider.provider_name,
                status="succeeded",
                attempt_count=0,
                started_at=datetime.now(UTC),
                finished_at=datetime.now(UTC),
                version="v1",
            )
            db.add(run)
            db.commit()
            return run

        # 2. Initialize EnrichmentRun
        run = EnrichmentRun(
            company_id=company.id,
            provider=self.provider.provider_name,
            status="running",
            attempt_count=0,
            started_at=datetime.now(UTC),
            version="v1",
        )
        db.add(run)
        db.flush()

        company.record_status = "enriching"
        db.commit()

        attempt = 0
        last_result: ProviderResult | None = None

        while attempt < self.max_retries:
            attempt += 1
            run.attempt_count = attempt

            last_result = self.provider.fetch_company_data(company.normalized_domain)

            if last_result.success and last_result.raw_text:
                # Success! Persist evidence
                EvidenceService.persist_evidence(
                    db=db,
                    company_id=company.id,
                    source_type=self.provider.provider_name,
                    raw_text=last_result.raw_text,
                    source_url=last_result.source_url,
                    metadata_json=last_result.metadata,
                )

                run.status = "succeeded"
                run.finished_at = datetime.now(UTC)
                company.record_status = "enriched"
                if not company.description:
                    company.description = last_result.raw_text[:300].strip()

                db.commit()
                return run

            # Non-retryable permanent failure (e.g. 404 Not Found, 403 Forbidden)
            if not last_result.is_retryable:
                run.status = "permanent_failed"
                run.error_type = last_result.error_type
                run.error_message = last_result.error_message
                run.finished_at = datetime.now(UTC)
                company.record_status = "enrichment_failed"

                db.commit()
                return run

            # Retryable error: backoff if attempts remaining
            if attempt < self.max_retries:
                delay = self._calculate_backoff(attempt, last_result.retry_after)
                logger.warning(
                    f"Retryable error enriching {company.normalized_domain} (attempt {attempt}/{self.max_retries}): "
                    f"{last_result.error_type}. Backing off for {delay:.2f}s."
                )
                time.sleep(delay)

        # Max retries exhausted
        run.status = "retryable_failed"
        run.error_type = last_result.error_type if last_result else "MaxRetriesExceeded"
        run.error_message = (
            last_result.error_message if last_result else "Exceeded maximum retry attempts"
        )
        run.finished_at = datetime.now(UTC)
        company.record_status = "enrichment_failed"

        db.commit()
        return run

    def enrich_batch(
        self,
        db: Session,
        companies: list[Company],
        force_refresh: bool = False,
    ) -> EnrichmentBatchSummary:
        """Enrich a batch of companies with partial failure isolation.

        A failure in one company never cancels or rolls back other companies in the batch.
        """
        summary = EnrichmentBatchSummary(total_companies=len(companies))

        for comp in companies:
            try:
                run = self.enrich_company(db, comp, force_refresh=force_refresh)
                summary.run_ids.append(run.id)

                if run.attempt_count == 0 and run.status == "succeeded":
                    summary.skipped_fresh += 1
                elif run.status == "succeeded":
                    summary.succeeded += 1
                else:
                    summary.failed += 1
                    summary.errors.append(
                        {
                            "company_id": str(comp.id),
                            "domain": comp.normalized_domain,
                            "error_type": run.error_type,
                            "error_message": run.error_message,
                        }
                    )
            except Exception as exc:  # noqa: BLE001 - shield batch from unexpected record failures
                summary.failed += 1
                summary.errors.append(
                    {
                        "company_id": str(comp.id),
                        "domain": comp.normalized_domain,
                        "error_type": type(exc).__name__,
                        "error_message": str(exc),
                    }
                )
                logger.error(
                    f"Unexpected error processing company {comp.normalized_domain}: {exc}",
                    exc_info=True,
                )

        return summary
