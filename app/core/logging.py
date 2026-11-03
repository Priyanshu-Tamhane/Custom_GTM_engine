"""Structured logging system with contextual metadata and secret masking."""

import json
import logging
import sys
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

# Context variables for tracing requests and background jobs
request_id_ctx: ContextVar[str | None] = ContextVar("request_id", default=None)
job_id_ctx: ContextVar[str | None] = ContextVar("job_id", default=None)
company_id_ctx: ContextVar[str | None] = ContextVar("company_id", default=None)
campaign_id_ctx: ContextVar[str | None] = ContextVar("campaign_id", default=None)

# Sensitive keys to redact
SENSITIVE_KEYS = {"password", "secret", "token", "api_key", "authorization", "llm_api_key"}


class JSONFormatter(logging.Formatter):
    """Formats log records as structured JSON with contextual tracking fields."""

    def format(self, record: logging.LogRecord) -> str:
        log_data: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Include contextual IDs if available
        req_id = request_id_ctx.get()
        if req_id:
            log_data["request_id"] = req_id

        job_id = job_id_ctx.get()
        if job_id:
            log_data["job_id"] = job_id

        comp_id = company_id_ctx.get()
        if comp_id:
            log_data["company_id"] = comp_id

        camp_id = campaign_id_ctx.get()
        if camp_id:
            log_data["campaign_id"] = camp_id

        # Attach extra structured fields passed in record
        if hasattr(record, "extra_fields") and isinstance(record.extra_fields, dict):
            for k, v in record.extra_fields.items():
                if any(sens in k.lower() for sens in SENSITIVE_KEYS):
                    log_data[k] = "***REDACTED***"
                else:
                    log_data[k] = v

        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_data)


def setup_logging(log_level: str = "INFO") -> logging.Logger:
    """Configure root and application loggers."""
    root_logger = logging.getLogger()
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)
    root_logger.setLevel(numeric_level)

    # Avoid duplicate handlers
    if not root_logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JSONFormatter())
        root_logger.addHandler(handler)
    else:
        for handler in root_logger.handlers:
            handler.setFormatter(JSONFormatter())

    app_logger = logging.getLogger("gtm_engine")
    app_logger.setLevel(numeric_level)
    return app_logger


logger = logging.getLogger("gtm_engine")
