"""Custom application domain exceptions."""


class GTMAppException(Exception):
    """Base exception for all GTM Intelligence Engine errors."""

    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}


class EntityNotFoundError(GTMAppException):
    """Raised when a requested database entity is not found."""


class DuplicateEntityError(GTMAppException):
    """Raised when an entity violates unique constraints."""


class ValidationError(GTMAppException):
    """Raised when domain or CSV input validation fails."""


class ProviderError(GTMAppException):
    """Base class for third-party provider adapter failures."""

    def __init__(
        self, message: str, provider: str, retryable: bool = False, details: dict | None = None
    ):
        super().__init__(message, details)
        self.provider = provider
        self.retryable = retryable


class ProviderRateLimitError(ProviderError):
    """Raised when an external API rate limit (HTTP 429) is encountered."""

    def __init__(
        self,
        message: str,
        provider: str,
        retry_after: float | None = None,
        details: dict | None = None,
    ):
        super().__init__(message, provider, retryable=True, details=details)
        self.retry_after = retry_after


class ProviderTimeoutError(ProviderError):
    """Raised when an external API request times out."""

    def __init__(self, message: str, provider: str, details: dict | None = None):
        super().__init__(message, provider, retryable=True, details=details)


class UnsupportedClaimError(GTMAppException):
    """Raised when an AI-generated draft includes claims not backed by verified evidence."""
