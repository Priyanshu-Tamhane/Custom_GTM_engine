"""Unit tests for deterministic MockLLMProvider and its fault injection modes."""

import json

import pytest

from app.core.exceptions import ProviderRateLimitError, ProviderTimeoutError
from app.providers.llm.mock_llm import MockLLMProvider


def test_mock_llm_success_extraction():
    """Verify default successful extraction returns valid JSON schema."""
    llm = MockLLMProvider()
    response = llm.generate_structured_json(
        system_prompt="Extract facts",
        user_prompt='domain: vanta.com\n<untrusted_web_evidence id="11111111-1111-1111-1111-111111111111">Vanta automates compliance</untrusted_web_evidence>',
    )

    assert response.model_name == "mock-llama-3.3-70b"
    assert response.input_tokens > 0
    assert response.output_tokens > 0
    assert response.estimated_cost_usd > 0.0

    parsed = json.loads(response.raw_json)
    assert parsed["company_name"] == "Vanta"
    assert parsed["industry"]["value"] == "B2B SaaS"
    assert parsed["industry"]["evidence_ids"] == ["11111111-1111-1111-1111-111111111111"]


def test_mock_llm_rate_limit_scenario():
    """Verify rate limit scenario raises ProviderRateLimitError with retry_after."""
    llm = MockLLMProvider(default_scenario="rate_limit")

    with pytest.raises(ProviderRateLimitError) as exc_info:
        llm.generate_structured_json("system", "domain: test.com")

    assert exc_info.value.provider == "mock_llm"
    assert exc_info.value.retry_after == 0.1
    assert exc_info.value.retryable is True


def test_mock_llm_timeout_scenario():
    """Verify timeout scenario raises ProviderTimeoutError."""
    llm = MockLLMProvider(default_scenario="timeout")

    with pytest.raises(ProviderTimeoutError) as exc_info:
        llm.generate_structured_json("system", "domain: test.com")

    assert exc_info.value.provider == "mock_llm"
    assert exc_info.value.retryable is True


def test_mock_llm_invalid_json_scenario():
    """Verify invalid_json scenario returns unparseable JSON string."""
    llm = MockLLMProvider(default_scenario="invalid_json")
    response = llm.generate_structured_json("system", "domain: test.com")

    with pytest.raises(json.JSONDecodeError):
        json.loads(response.raw_json)


def test_mock_llm_hallucinated_id_scenario():
    """Verify hallucinated_id scenario introduces an unreferenced UUID."""
    llm = MockLLMProvider(default_scenario="hallucinated_id")
    response = llm.generate_structured_json(
        "system",
        'domain: test.com\n<untrusted_web_evidence id="11111111-1111-1111-1111-111111111111">test</untrusted_web_evidence>',
    )

    data = json.loads(response.raw_json)
    # The industry citation contains 99999999-9999-9999-9999-999999999999
    assert "99999999-9999-9999-9999-999999999999" in data["industry"]["evidence_ids"]


def test_mock_llm_domain_override():
    """Verify per-domain scenario override functionality."""
    llm = MockLLMProvider(default_scenario="success")
    llm.set_scenario_for_domain("flaky.io", "timeout")

    # Regular domain succeeds
    res = llm.generate_structured_json("system", "domain: normal.com")
    assert json.loads(res.raw_json)["company_name"] == "Normal"

    # Overridden domain times out
    with pytest.raises(ProviderTimeoutError):
        llm.generate_structured_json("system", "domain: flaky.io")
