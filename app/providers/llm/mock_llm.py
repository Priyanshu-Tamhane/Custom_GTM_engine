"""Deterministic Mock LLM provider for offline testing and guardrail verification."""

import json
import re
import time

from app.core.exceptions import ProviderRateLimitError, ProviderTimeoutError
from app.providers.llm.base import BaseLLMProvider, LLMResponse


class MockLLMProvider(BaseLLMProvider):
    """Mock LLM adapter returning pre-canned structured JSON extractions."""

    def __init__(
        self,
        model_name: str = "mock-llama-3.3-70b",
        default_scenario: str = "success",
        timeout_seconds: float = 2.0,
    ):
        super().__init__(model_name=model_name, timeout_seconds=timeout_seconds)
        self.default_scenario = default_scenario
        self.domain_scenarios: dict[str, str] = {}
        self.call_count: int = 0

    def set_scenario_for_domain(self, domain: str, scenario: str) -> None:
        """Override scenario for a specific domain."""
        self.domain_scenarios[domain] = scenario

    def generate_structured_json(self, system_prompt: str, user_prompt: str) -> LLMResponse:
        """Simulate LLM response according to configured scenario."""
        self.call_count += 1
        start_time = time.perf_counter()

        # Extract domain from user_prompt if present
        domain_match = re.search(r"domain:\s*([a-zA-Z0-9.-]+)", user_prompt, re.IGNORECASE)
        domain = domain_match.group(1).lower() if domain_match else "example.com"

        # Extract evidence ID from prompt if present
        ev_id_match = re.search(r'id="([a-f0-9\-]+)"', user_prompt)
        evidence_id = ev_id_match.group(1) if ev_id_match else "11111111-1111-1111-1111-111111111111"

        scenario = self.domain_scenarios.get(domain, self.default_scenario)

        if scenario == "timeout":
            raise ProviderTimeoutError(
                message=f"Mock LLM call timed out after {self.timeout_seconds}s",
                provider="mock_llm",
            )

        if scenario == "rate_limit":
            raise ProviderRateLimitError(
                message="Mock LLM rate limit exceeded (HTTP 429)",
                provider="mock_llm",
                retry_after=0.1,
            )

        if scenario == "invalid_json":
            latency = (time.perf_counter() - start_time) * 1000
            return LLMResponse(
                raw_json="{malformed json, missing braces",
                model_name=self.model_name,
                input_tokens=150,
                output_tokens=15,
                latency_ms=round(latency, 2),
                estimated_cost_usd=0.0001,
            )

        if scenario == "hallucinated_id":
            # Model invents an evidence ID that doesn't exist
            latency = (time.perf_counter() - start_time) * 1000
            payload = {
                "company_name": "Hallucinating Co",
                "description": "Company with invented citations.",
                "industry": {
                    "value": "B2B SaaS",
                    "confidence": 0.9,
                    "evidence_ids": ["99999999-9999-9999-9999-999999999999"],  # FAKE ID!
                },
                "employee_range": {
                    "value": "50-100",
                    "confidence": 0.8,
                    "evidence_ids": [evidence_id],
                },
                "relevant_signals": [],
                "unknown_fields": [],
                "needs_human_review": False,
            }
            return LLMResponse(
                raw_json=json.dumps(payload),
                model_name=self.model_name,
                input_tokens=200,
                output_tokens=80,
                latency_ms=round(latency, 2),
                estimated_cost_usd=0.0001,
            )

        # Default: Success extraction
        latency = (time.perf_counter() - start_time) * 1000

        # Custom profile responses for known benchmark domains
        if "vanta" in domain:
            payload = {
                "company_name": "Vanta",
                "description": "Automated security and compliance platform for SaaS businesses.",
                "industry": {
                    "value": "B2B SaaS",
                    "confidence": 0.95,
                    "evidence_ids": [evidence_id],
                },
                "employee_range": {
                    "value": "200-300",
                    "confidence": 0.90,
                    "evidence_ids": [evidence_id],
                },
                "relevant_signals": [
                    {
                        "signal": "public support/help center",
                        "confidence": 0.95,
                        "evidence_ids": [evidence_id],
                    },
                    {
                        "signal": "customer success desk",
                        "confidence": 0.90,
                        "evidence_ids": [evidence_id],
                    },
                ],
                "unknown_fields": ["pricing_tiers"],
                "needs_human_review": False,
            }
        elif "incident" in domain:
            payload = {
                "company_name": "incident.io",
                "description": "Incident management and automated alerting platform for modern tech teams.",
                "industry": {
                    "value": "B2B SaaS",
                    "confidence": 0.95,
                    "evidence_ids": [evidence_id],
                },
                "employee_range": {
                    "value": "50-100",
                    "confidence": 0.80,
                    "evidence_ids": [evidence_id],
                },
                "relevant_signals": [
                    {
                        "signal": "public support/help center",
                        "confidence": 0.95,
                        "evidence_ids": [evidence_id],
                    }
                ],
                "unknown_fields": ["exact_support_team_count"],
                "needs_human_review": False,
            }
        else:
            payload = {
                "company_name": domain.split(".")[0].capitalize(),
                "description": f"{domain} digital software and technology services.",
                "industry": {
                    "value": "B2B SaaS",
                    "confidence": 0.75,
                    "evidence_ids": [evidence_id],
                },
                "employee_range": {
                    "value": "20-100",
                    "confidence": 0.65,
                    "evidence_ids": [evidence_id],
                },
                "relevant_signals": [
                    {
                        "signal": "public support/help center",
                        "confidence": 0.80,
                        "evidence_ids": [evidence_id],
                    }
                ],
                "unknown_fields": ["annual_revenue"],
                "needs_human_review": False,
            }

        return LLMResponse(
            raw_json=json.dumps(payload),
            model_name=self.model_name,
            input_tokens=250,
            output_tokens=110,
            latency_ms=round(latency, 2),
            estimated_cost_usd=0.00015,
        )
