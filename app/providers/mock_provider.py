"""Mock enrichment provider for offline testing and controlled failure simulation."""

from app.providers.base import BaseEnrichmentProvider, ProviderResult

# Pre-canned realistic text for benchmark companies
BENCHMARK_PROFILES: dict[str, str] = {
    "incident.io": (
        "incident.io is an incident management platform built for modern software engineering teams. "
        "We help high-growth tech companies automate alerts, coordinate response in Slack, and conduct "
        "blameless post-mortems. Our 24/7 dedicated customer support team and comprehensive help center "
        "ensure enterprise reliability for over 500 tech customers."
    ),
    "vanta.com": (
        "Vanta automates security and compliance for cloud software businesses. Over 7,000 customers "
        "use Vanta to achieve SOC 2, ISO 27001, HIPAA, and GDPR compliance. Vanta employs over 280 team members "
        "with an active customer success desk, live chat support, and dedicated compliance advisors."
    ),
    "linear.app": (
        "Linear is a project management tool purpose-built for high-performance software teams. "
        "It features instant sync, offline support, and git integrations. Linear maintains an extensive "
        "documentation portal and active user support channels for its 45-person team."
    ),
    "attio.com": (
        "Attio is a flexible CRM for modern tech companies and startups. Our team of 50 provides "
        "support via documentation, in-app chat, and onboarding guidance."
    ),
    "posthog.com": (
        "PostHog provides all-in-one developer analytics, feature flags, session recording, and A/B testing. "
        "With 75 employees, PostHog provides comprehensive developer docs and a community support forum."
    ),
    "stealth-ai-research.internal": (
        "Stealth AI Research. Domain active. No public product, pricing, or customer support channels found."
    ),
}


class MockEnrichmentProvider(BaseEnrichmentProvider):
    """Configurable mock provider supporting transient errors, rate limits, and flaky retries."""

    def __init__(
        self,
        provider_name: str = "mock_provider",
        default_scenario: str = "success",
        timeout_seconds: float = 1.0,
    ):
        super().__init__(provider_name=provider_name, timeout_seconds=timeout_seconds)
        self.default_scenario = default_scenario
        self.domain_scenarios: dict[str, str] = {}
        self.domain_call_counts: dict[str, int] = {}
        self.flaky_success_threshold: int = 2  # Succeed on 2nd attempt by default

    def set_domain_scenario(self, domain: str, scenario: str) -> None:
        """Override scenario for a specific domain (e.g. 'timeout', 'rate_limit', 'not_found')."""
        self.domain_scenarios[domain] = scenario

    def fetch_company_data(self, domain: str) -> ProviderResult:
        """Simulate company fetch based on configured scenario."""
        count = self.domain_call_counts.get(domain, 0) + 1
        self.domain_call_counts[domain] = count

        scenario = self.domain_scenarios.get(domain, self.default_scenario)

        if scenario == "timeout":
            return ProviderResult(
                domain=domain,
                provider=self.provider_name,
                success=False,
                is_retryable=True,
                error_type="TimeoutError",
                error_message=f"Request timed out after {self.timeout_seconds}s connecting to {domain}",
            )

        if scenario == "rate_limit":
            return ProviderResult(
                domain=domain,
                provider=self.provider_name,
                success=False,
                status_code=429,
                is_retryable=True,
                retry_after=0.01,
                error_type="HTTP_429_RateLimit",
                error_message="Rate limit exceeded. Too many requests.",
            )

        if scenario == "not_found":
            return ProviderResult(
                domain=domain,
                provider=self.provider_name,
                success=False,
                status_code=404,
                is_retryable=False,
                error_type="HTTP_404_NotFound",
                error_message=f"Domain {domain} returned HTTP 404 Not Found",
            )

        if scenario == "server_error":
            return ProviderResult(
                domain=domain,
                provider=self.provider_name,
                success=False,
                status_code=503,
                is_retryable=True,
                error_type="HTTP_503_ServiceUnavailable",
                error_message="Upstream service unavailable",
            )

        if scenario == "flaky" and count < self.flaky_success_threshold:
            return ProviderResult(
                domain=domain,
                provider=self.provider_name,
                success=False,
                is_retryable=True,
                error_type="TimeoutError",
                error_message=f"Simulated transient timeout (attempt {count})",
            )
            # Then succeed!

        # Default Success scenario
        profile_text = BENCHMARK_PROFILES.get(
            domain,
            f"{domain} is a technology company offering digital software products and solutions. "
            f"The company provides public help documentation and customer support contact channels.",
        )

        return ProviderResult(
            domain=domain,
            provider=self.provider_name,
            success=True,
            status_code=200,
            source_url=f"https://{domain}",
            raw_text=profile_text,
            is_retryable=False,
            metadata={"call_count": count, "mode": "mock"},
        )
