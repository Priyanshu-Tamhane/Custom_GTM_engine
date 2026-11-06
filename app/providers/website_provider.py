"""Website text fetcher provider adapter with HTML sanitization and error categorization."""

import re

import httpx
from bs4 import BeautifulSoup

from app.providers.base import BaseEnrichmentProvider, ProviderResult

STRIP_TAGS = {"script", "style", "noscript", "svg", "header", "footer", "nav", "aside"}


class WebsiteEnrichmentProvider(BaseEnrichmentProvider):
    """Fetches public homepage/about content from permitted company websites."""

    def __init__(
        self,
        provider_name: str = "website_fetcher",
        timeout_seconds: float = 10.0,
        user_agent: str = "GTM-Intelligence-Engine/0.1.0 (B2B Research)",
    ):
        super().__init__(provider_name=provider_name, timeout_seconds=timeout_seconds)
        self.user_agent = user_agent

    def _extract_clean_text(self, html: str) -> str:
        """Parse HTML and extract readable text without scripts or styling."""
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup.find_all(STRIP_TAGS):
            tag.decompose()

        text = soup.get_text(separator=" ")
        # Collapse multiple spaces and linebreaks
        return re.sub(r"\s+", " ", text).strip()

    def fetch_company_data(self, domain: str) -> ProviderResult:
        """Fetch and extract clean text from the target domain."""
        url = f"https://{domain}"
        headers = {"User-Agent": self.user_agent, "Accept": "text/html,application/xhtml+xml"}

        try:
            with httpx.Client(timeout=self.timeout_seconds, follow_redirects=True) as client:
                response = client.get(url, headers=headers)
                response.raise_for_status()

            clean_text = self._extract_clean_text(response.text)
            return ProviderResult(
                domain=domain,
                provider=self.provider_name,
                success=True,
                source_url=str(response.url),
                raw_text=clean_text[:5000],  # Bound text length
                status_code=response.status_code,
                is_retryable=False,
                metadata={"content_length": len(clean_text)},
            )

        except httpx.TimeoutException as exc:
            return ProviderResult(
                domain=domain,
                provider=self.provider_name,
                success=False,
                source_url=url,
                is_retryable=True,
                error_type="TimeoutError",
                error_message=f"Request timed out after {self.timeout_seconds}s: {exc}",
            )

        except httpx.HTTPStatusError as exc:
            code = exc.response.status_code
            retry_after: float | None = None
            if "Retry-After" in exc.response.headers:
                try:
                    retry_after = float(exc.response.headers["Retry-After"])
                except ValueError:
                    retry_after = None

            is_retryable = code == 429 or code >= 500
            err_type = (
                "HTTP_429_RateLimit"
                if code == 429
                else (f"HTTP_{code}_ServerError" if code >= 500 else f"HTTP_{code}_ClientError")
            )

            return ProviderResult(
                domain=domain,
                provider=self.provider_name,
                success=False,
                source_url=url,
                status_code=code,
                is_retryable=is_retryable,
                retry_after=retry_after,
                error_type=err_type,
                error_message=f"HTTP {code} received from {url}",
            )

        except httpx.RequestError as exc:
            return ProviderResult(
                domain=domain,
                provider=self.provider_name,
                success=False,
                source_url=url,
                is_retryable=False,
                error_type="NetworkError",
                error_message=f"Network connection failed: {exc}",
            )

        except Exception as exc:  # noqa: BLE001 - catch unexpected network exceptions cleanly
            return ProviderResult(
                domain=domain,
                provider=self.provider_name,
                success=False,
                source_url=url,
                is_retryable=False,
                error_type=type(exc).__name__,
                error_message=str(exc),
            )
