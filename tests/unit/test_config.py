"""Unit tests for configuration and logging."""

import json
import logging

from app.core.config import Settings
from app.core.logging import JSONFormatter, request_id_ctx


def test_settings_defaults():
    settings = Settings()
    assert settings.PROJECT_NAME == "GTM Intelligence Engine"
    assert settings.VERSION == "0.1.0"
    assert settings.RATE_LIMIT_PER_MINUTE == 60


def test_logging_masks_secrets():
    formatter = JSONFormatter()
    record = logging.LogRecord(
        name="test_logger",
        level=logging.INFO,
        pathname="test.py",
        lineno=10,
        msg="Test operation",
        args=(),
        exc_info=None,
    )
    record.extra_fields = {
        "api_key": "super_secret_12345",
        "normal_field": "public_data",
    }

    formatted = formatter.format(record)
    data = json.loads(formatted)

    assert data["message"] == "Test operation"
    assert data["normal_field"] == "public_data"
    assert data["api_key"] == "***REDACTED***"


def test_logging_context_ids():
    formatter = JSONFormatter()
    token = request_id_ctx.set("req_abc_123")
    try:
        record = logging.LogRecord(
            name="test_logger",
            level=logging.INFO,
            pathname="test.py",
            lineno=10,
            msg="Request received",
            args=(),
            exc_info=None,
        )
        formatted = formatter.format(record)
        data = json.loads(formatted)
        assert data["request_id"] == "req_abc_123"
    finally:
        request_id_ctx.reset(token)
