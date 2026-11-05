"""Domain normalization engine for conservative, reproducible company account keys."""

import re
import urllib.parse

from app.core.exceptions import ValidationError

# RFC 1035 / RFC 1123 compliant hostname label regex
LABEL_REGEX = re.compile(r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$")

DISALLOWED_SCHEMES = ("ftp://", "file://", "javascript:", "data:")


def normalize_domain(raw_domain: str | None) -> str:
    """Normalize a domain or website URL into a canonical hostname.

    Rules:
    - Strips leading/trailing whitespace.
    - Strips scheme (http://, https://). Rejects non-HTTP schemes (ftp, file, etc.).
    - Strips port (:443, :8080), path (/about), query (?ref=1), and fragments (#top).
    - Lowercases hostname.
    - Strips leading 'www.' prefix.
    - Validates hostname structure (no consecutive dots, valid alphanumeric labels, length limits).
    - Rejects empty or malformed domain values.

    Args:
        raw_domain: Raw input string (e.g. "https://WWW.Vanta.com:443/about").

    Returns:
        Clean normalized domain string (e.g. "vanta.com").

    Raises:
        ValidationError: If domain is empty, malformed, or has an unsupported protocol.
    """
    if raw_domain is None or not isinstance(raw_domain, str):
        raise ValidationError("Domain value is required and cannot be empty")

    cleaned = raw_domain.strip()
    if not cleaned:
        raise ValidationError("Domain value cannot be empty or whitespace only")

    # Reject unsupported schemes
    if cleaned.lower().startswith(DISALLOWED_SCHEMES):
        raise ValidationError(f"Unsupported protocol scheme in domain: {cleaned}")

    # Ensure URL parser can process bare domains
    if not re.match(r"^[a-zA-Z0-9+.-]+://", cleaned):
        cleaned = "http://" + cleaned

    try:
        parsed = urllib.parse.urlparse(cleaned)
    except Exception as exc:
        raise ValidationError(f"Failed to parse domain URL: {exc}") from exc

    if parsed.scheme.lower() not in ("http", "https"):
        raise ValidationError(f"Invalid URL protocol scheme: {parsed.scheme}")

    hostname = parsed.hostname
    if not hostname:
        raise ValidationError("No valid hostname found in domain input")

    hostname = hostname.lower().strip(".")

    # Structural validations
    if ".." in hostname:
        raise ValidationError(f"Domain contains consecutive dots: {hostname}")

    # Remove leading 'www.'
    hostname = hostname.removeprefix("www.")

    parts = hostname.split(".")
    if len(parts) < 2:
        raise ValidationError(f"Domain must contain at least a name and extension: {hostname}")

    for part in parts:
        if not part or not LABEL_REGEX.match(part):
            raise ValidationError(f"Invalid domain label '{part}' in domain: {hostname}")

    # Check top-level domain length
    if len(parts[-1]) < 2:
        raise ValidationError(f"Invalid top-level domain suffix in domain: {hostname}")

    if len(hostname) > 253:
        raise ValidationError(f"Domain length exceeds maximum RFC limit (253 chars): {hostname}")

    return hostname
