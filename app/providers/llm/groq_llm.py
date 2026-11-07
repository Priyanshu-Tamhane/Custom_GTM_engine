"""Groq LLM provider adapter using official Groq Python SDK with JSON mode."""

import os
import time
from typing import Any

import groq

from app.core.config import get_settings
from app.core.exceptions import ProviderError, ProviderRateLimitError, ProviderTimeoutError
from app.core.logging import get_logger
from app.providers.llm.base import BaseLLMProvider, LLMResponse

logger = get_logger("groq_llm_provider")


class GroqLLMProvider(BaseLLMProvider):
    """Adapter for Groq Cloud API featuring fast inference and structured JSON mode."""

    def __init__(
        self,
        api_key: str | None = None,
        model_name: str | None = None,
        timeout_seconds: float = 30.0,
        client: Any | None = None,
    ):
        settings = get_settings()
        resolved_model = model_name or settings.GROQ_MODEL or "llama-3.3-70b-versatile"
        super().__init__(model_name=resolved_model, timeout_seconds=timeout_seconds)

        # Resolve API key from argument, settings, or environment
        if api_key:
            self.api_key = api_key
        elif settings.GROQ_API_KEY:
            self.api_key = settings.GROQ_API_KEY.get_secret_value()
        else:
            self.api_key = os.environ.get("GROQ_API_KEY", "")

        # Optional injected client for testing/mocking
        if client is not None:
            self._client = client
        elif self.api_key:
            self._client = groq.Groq(api_key=self.api_key, timeout=self.timeout_seconds)
        else:
            self._client = None

    @property
    def client(self) -> groq.Groq:
        """Lazy-initialize or return client; raises ProviderError if no key configured."""
        if self._client is not None:
            return self._client
        if not self.api_key:
            raise ProviderError(
                message="Groq API key is not configured. Set GROQ_API_KEY in environment or .env",
                provider="groq",
                retryable=False,
            )
        self._client = groq.Groq(api_key=self.api_key, timeout=self.timeout_seconds)
        return self._client

    def _calculate_cost(self, prompt_tokens: int, completion_tokens: int) -> float:
        """Estimate inference cost in USD based on Groq pricing."""
        if "8b" in self.model_name.lower():
            # Llama-3.1-8b: ~$0.05 / 1M prompt, $0.08 / 1M completion
            rate_in = 0.05 / 1_000_000
            rate_out = 0.08 / 1_000_000
        else:
            # Llama-3.3-70b: ~$0.59 / 1M prompt, $0.79 / 1M completion
            rate_in = 0.59 / 1_000_000
            rate_out = 0.79 / 1_000_000

        return round((prompt_tokens * rate_in) + (completion_tokens * rate_out), 6)

    def generate_structured_json(self, system_prompt: str, user_prompt: str) -> LLMResponse:
        """Invoke Groq with JSON mode enabled, translating provider errors into domain exceptions.

        Args:
            system_prompt: Operational schema, role, and injection defense instructions.
            user_prompt: Isolated untrusted evidence text.

        Returns:
            LLMResponse containing raw JSON string, token counts, latency, and estimated cost.
        """
        start_time = time.perf_counter()

        logger.debug(
            f"Calling Groq LLM model={self.model_name} timeout={self.timeout_seconds}"
        )

        try:
            chat_completion = self.client.chat.completions.create(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                model=self.model_name,
                response_format={"type": "json_object"},
                temperature=0.0,
                timeout=self.timeout_seconds,
            )
        except groq.RateLimitError as e:
            logger.warning(f"Groq rate limit encountered: {e}")
            retry_after = getattr(e, "retry_after", None)
            raise ProviderRateLimitError(
                message=f"Groq rate limit exceeded: {e}",
                provider="groq",
                retry_after=float(retry_after) if retry_after else 5.0,
            ) from e
        except groq.APITimeoutError as e:
            logger.warning(f"Groq call timed out: {e}")
            raise ProviderTimeoutError(
                message=f"Groq request timed out after {self.timeout_seconds}s: {e}",
                provider="groq",
            ) from e
        except groq.APIConnectionError as e:
            logger.warning(f"Groq connection error: {e}")
            raise ProviderError(
                message=f"Groq connection failed: {e}",
                provider="groq",
                retryable=True,
            ) from e
        except groq.APIStatusError as e:
            status_code = getattr(e, "status_code", 500)
            is_server_error = status_code >= 500
            logger.warning(f"Groq API status error ({status_code}): {e}")
            raise ProviderError(
                message=f"Groq API error ({status_code}): {e}",
                provider="groq",
                retryable=is_server_error,
            ) from e
        except ProviderError:
            raise
        except Exception as e:
            logger.error(f"Unexpected Groq error: {e}")
            raise ProviderError(
                message=f"Unexpected Groq provider error: {e}",
                provider="groq",
                retryable=False,
            ) from e

        duration_ms = (time.perf_counter() - start_time) * 1000

        raw_content = ""
        if chat_completion.choices and len(chat_completion.choices) > 0:
            raw_content = chat_completion.choices[0].message.content or "{}"

        prompt_tokens = 0
        completion_tokens = 0
        if chat_completion.usage:
            prompt_tokens = chat_completion.usage.prompt_tokens or 0
            completion_tokens = chat_completion.usage.completion_tokens or 0

        estimated_cost = self._calculate_cost(prompt_tokens, completion_tokens)

        logger.info(
            f"Groq inference completed model={self.model_name} latency_ms={round(duration_ms, 2)} "
            f"prompt_tokens={prompt_tokens} completion_tokens={completion_tokens} cost_usd={estimated_cost}"
        )

        return LLMResponse(
            raw_json=raw_content,
            model_name=self.model_name,
            input_tokens=prompt_tokens,
            output_tokens=completion_tokens,
            latency_ms=round(duration_ms, 2),
            estimated_cost_usd=estimated_cost,
        )
