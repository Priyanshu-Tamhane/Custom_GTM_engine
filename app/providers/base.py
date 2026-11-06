"""Base provider interfaces and result structures for company enrichment."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass
class ProviderResult:
    """Structured result returned by any enrichment provider adapter."""

    domain: str
    provider: str
    success: bool
    source_url: str | None = None
    raw_text: str | None = None
    status_code: int | None = None
    is_retryable: bool = False
    error_type: str | None = None
    error_message: str | None = None
    retry_after: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    fetched_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class BaseEnrichmentProvider(ABC):
    """Abstract contract for all company enrichment data sources."""

    def __init__(self, provider_name: str, timeout_seconds: float = 10.0):
        self.provider_name = provider_name
        self.timeout_seconds = timeout_seconds

    @abstractmethod
    def fetch_company_data(self, domain: str) -> ProviderResult:
        """Fetch company information and raw evidence for a given normalized domain.

        Args:
            domain: Canonical normalized domain (e.g. 'vanta.com').

        Returns:
            ProviderResult containing status, raw text, and error classifications.
        """
