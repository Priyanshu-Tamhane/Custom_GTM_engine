"""Unit tests for domain normalization engine."""

import pytest

from app.core.exceptions import ValidationError
from app.services.normalizer import normalize_domain


def test_clean_domain_passthrough():
    assert normalize_domain("incident.io") == "incident.io"
    assert normalize_domain("vanta.com") == "vanta.com"
    assert normalize_domain("linear.app") == "linear.app"


def test_scheme_and_www_stripping():
    assert normalize_domain("https://www.vanta.com") == "vanta.com"
    assert normalize_domain("http://WWW.VANTA.COM") == "vanta.com"
    assert normalize_domain("https://vanta.com/") == "vanta.com"


def test_path_port_and_query_removal():
    assert normalize_domain("http://linear.app:443/pricing") == "linear.app"
    assert normalize_domain("https://linear.app:8080/teams/join?ref=xyz#top") == "linear.app"
    assert normalize_domain("www.posthog.com/docs/product-analytics") == "posthog.com"


def test_subdomains_preserved_except_www():
    assert normalize_domain("app.incident.io") == "app.incident.io"
    assert normalize_domain("https://www.app.incident.io") == "app.incident.io"


def test_whitespace_trimmed():
    assert normalize_domain("   attio.com   ") == "attio.com"
    assert normalize_domain("\thttps://plane.so\n") == "plane.so"


def test_malformed_domain_rejected():
    with pytest.raises(ValidationError, match="consecutive dots"):
        normalize_domain("not-a-valid-domain..com")

    with pytest.raises(ValidationError, match="Unsupported protocol scheme"):
        normalize_domain("ftp://something/invalid")

    with pytest.raises(ValidationError, match="empty or whitespace"):
        normalize_domain("")

    with pytest.raises(ValidationError, match="empty or whitespace"):
        normalize_domain("   ")

    with pytest.raises(ValidationError, match="required and cannot be empty"):
        normalize_domain(None)


def test_single_label_and_invalid_chars():
    with pytest.raises(ValidationError, match="at least a name and extension"):
        normalize_domain("localhost")

    with pytest.raises(ValidationError, match="Invalid domain label"):
        normalize_domain("my_company.com")  # Underscores are not valid in domain labels
