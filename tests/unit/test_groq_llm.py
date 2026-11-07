"""Unit tests for GroqLLMProvider adapter with mocked Groq SDK client."""

from unittest.mock import MagicMock

import groq
import pytest

from app.core.exceptions import ProviderError, ProviderRateLimitError, ProviderTimeoutError
from app.providers.llm.groq_llm import GroqLLMProvider


def test_groq_missing_api_key_raises_error():
    """Verify provider raises clean domain ProviderError when API key is not configured."""
    provider = GroqLLMProvider(api_key="", client=None)
    # Clear internal client to test error on property access
    provider._client = None

    with pytest.raises(ProviderError) as exc_info:
        _ = provider.client

    assert "Groq API key is not configured" in exc_info.value.message
    assert exc_info.value.provider == "groq"


def test_groq_generate_structured_json_success():
    """Verify successful Groq inference with JSON response, token counts, and cost calculation."""
    mock_client = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = '{"company_name": "TestCorp", "description": "Security software"}'

    mock_usage = MagicMock()
    mock_usage.prompt_tokens = 500
    mock_usage.completion_tokens = 100

    mock_completion = MagicMock()
    mock_completion.choices = [mock_choice]
    mock_completion.usage = mock_usage

    mock_client.chat.completions.create.return_value = mock_completion

    provider = GroqLLMProvider(
        api_key="gsk_dummy_key",
        model_name="llama-3.3-70b-versatile",
        client=mock_client,
    )

    response = provider.generate_structured_json(
        system_prompt="System instructions",
        user_prompt="User prompt with evidence",
    )

    assert response.raw_json == '{"company_name": "TestCorp", "description": "Security software"}'
    assert response.model_name == "llama-3.3-70b-versatile"
    assert response.input_tokens == 500
    assert response.output_tokens == 100
    assert response.estimated_cost_usd > 0.0

    mock_client.chat.completions.create.assert_called_once_with(
        messages=[
            {"role": "system", "content": "System instructions"},
            {"role": "user", "content": "User prompt with evidence"},
        ],
        model="llama-3.3-70b-versatile",
        response_format={"type": "json_object"},
        temperature=0.0,
        timeout=30.0,
    )


def test_groq_8b_cost_calculation():
    """Verify cost calculation applies the lower 8B pricing tier."""
    provider = GroqLLMProvider(
        api_key="gsk_dummy",
        model_name="llama-3.1-8b-instant",
        client=MagicMock(),
    )
    # 1 million prompt tokens at $0.05 + 1 million completion tokens at $0.08 = $0.13
    cost = provider._calculate_cost(prompt_tokens=1_000_000, completion_tokens=1_000_000)
    assert cost == 0.13


def test_groq_rate_limit_error_translation():
    """Verify groq.RateLimitError translates to ProviderRateLimitError."""
    mock_client = MagicMock()
    # Mock RateLimitError
    mock_client.chat.completions.create.side_effect = groq.RateLimitError(
        message="Rate limit reached for model",
        response=MagicMock(status_code=429, headers={"retry-after": "3"}),
        body={"error": {"message": "Rate limit reached"}},
    )

    provider = GroqLLMProvider(api_key="gsk_dummy", client=mock_client)

    with pytest.raises(ProviderRateLimitError) as exc_info:
        provider.generate_structured_json("sys", "user")

    assert exc_info.value.provider == "groq"
    assert exc_info.value.retryable is True


def test_groq_timeout_error_translation():
    """Verify groq.APITimeoutError translates to ProviderTimeoutError."""
    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = groq.APITimeoutError(
        request=MagicMock()
    )

    provider = GroqLLMProvider(api_key="gsk_dummy", timeout_seconds=10.0, client=mock_client)

    with pytest.raises(ProviderTimeoutError) as exc_info:
        provider.generate_structured_json("sys", "user")

    assert exc_info.value.provider == "groq"
    assert exc_info.value.retryable is True
    assert "timed out after 10.0s" in exc_info.value.message


def test_groq_server_error_translation():
    """Verify groq.APIStatusError with 500 translates to retryable ProviderError."""
    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = groq.APIStatusError(
        message="Internal server error",
        response=MagicMock(status_code=503),
        body=None,
    )

    provider = GroqLLMProvider(api_key="gsk_dummy", client=mock_client)

    with pytest.raises(ProviderError) as exc_info:
        provider.generate_structured_json("sys", "user")

    assert exc_info.value.provider == "groq"
    assert exc_info.value.retryable is True
