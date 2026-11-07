"""Base LLM provider interfaces and response structures."""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class LLMResponse:
    """Structured response from an LLM inference call."""

    raw_json: str
    model_name: str
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: float = 0.0
    estimated_cost_usd: float = 0.0


class BaseLLMProvider(ABC):
    """Abstract contract for LLM provider adapters."""

    def __init__(self, model_name: str, timeout_seconds: float = 30.0):
        self.model_name = model_name
        self.timeout_seconds = timeout_seconds

    @abstractmethod
    def generate_structured_json(self, system_prompt: str, user_prompt: str) -> LLMResponse:
        """Call LLM with instructions and untrusted context to generate strict JSON.

        Args:
            system_prompt: Core operational and schema instructions.
            user_prompt: Isolated untrusted evidence text.

        Returns:
            LLMResponse containing raw JSON string, token counts, latency, and estimated cost.
        """
