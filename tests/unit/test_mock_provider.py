"""Unit tests for MockEnrichmentProvider and failure scenario simulation."""

from app.providers.mock_provider import MockEnrichmentProvider


def test_mock_provider_default_success():
    provider = MockEnrichmentProvider()
    res = provider.fetch_company_data("incident.io")

    assert res.success is True
    assert res.status_code == 200
    assert "incident.io" in res.raw_text
    assert "24/7 dedicated customer support" in res.raw_text
    assert res.is_retryable is False
    assert res.source_url == "https://incident.io"


def test_mock_provider_simulated_timeout():
    provider = MockEnrichmentProvider(default_scenario="timeout")
    res = provider.fetch_company_data("timeoutco.com")

    assert res.success is False
    assert res.is_retryable is True
    assert res.error_type == "TimeoutError"
    assert "timed out" in res.error_message


def test_mock_provider_simulated_rate_limit():
    provider = MockEnrichmentProvider(default_scenario="rate_limit")
    res = provider.fetch_company_data("ratelimitco.com")

    assert res.success is False
    assert res.status_code == 429
    assert res.is_retryable is True
    assert res.retry_after == 0.01
    assert res.error_type == "HTTP_429_RateLimit"


def test_mock_provider_simulated_not_found():
    provider = MockEnrichmentProvider(default_scenario="not_found")
    res = provider.fetch_company_data("deadco.xyz")

    assert res.success is False
    assert res.status_code == 404
    assert res.is_retryable is False
    assert res.error_type == "HTTP_404_NotFound"


def test_mock_provider_domain_override_and_flaky_retry():
    provider = MockEnrichmentProvider(default_scenario="success")
    provider.set_domain_scenario("flakyco.com", "flaky")
    provider.flaky_success_threshold = 2

    # Attempt 1: Fails
    res1 = provider.fetch_company_data("flakyco.com")
    assert res1.success is False
    assert res1.is_retryable is True
    assert "attempt 1" in res1.error_message

    # Attempt 2: Succeeds!
    res2 = provider.fetch_company_data("flakyco.com")
    assert res2.success is True
    assert res2.status_code == 200
