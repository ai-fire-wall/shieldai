"""
Structured logger — writes JSON-formatted logs and (optionally) persists to DB.
"""

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4


# ── JSON formatter ────────────────────────────────────────────────────────────

class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        log_obj: dict[str, Any] = {
            "ts":      datetime.now(timezone.utc).isoformat(),
            "level":   record.levelname,
            "logger":  record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            log_obj["exception"] = self.formatException(record.exc_info)
        if hasattr(record, "extra"):
            log_obj.update(record.extra)  # type: ignore[arg-type]
        return json.dumps(log_obj)


def get_logger(name: str = "ai_firewall") -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JSONFormatter())
        logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    return logger


# ── Request event logger ──────────────────────────────────────────────────────

logger = get_logger()


def generate_request_id() -> str:
    return str(uuid4())


def log_request_event(
    *,
    request_id: str,
    prompt_preview: str,            # first 120 chars only — never log full prompts
    provider: str,
    model: str,
    allowed: bool,
    input_threat_level: str,
    input_threats: list[str],
    output_threat_level: Optional[str] = None,
    output_issues: Optional[list[str]] = None,
    latency_ms: float,
    metadata: Optional[dict[str, Any]] = None,
) -> None:
    """
    Emit a structured log entry for every firewall transaction.
    In production this also persists to PostgreSQL via a background task.
    """
    logger.info(
        "firewall_request",
        extra={
            "extra": {
                "request_id":          request_id,
                "prompt_preview":      prompt_preview[:120],
                "provider":            provider,
                "model":               model,
                "allowed":             allowed,
                "input_threat_level":  input_threat_level,
                "input_threats":       input_threats,
                "output_threat_level": output_threat_level,
                "output_issues":       output_issues or [],
                "latency_ms":          round(latency_ms, 2),
                "metadata":            metadata or {},
            }
        },
    )


def log_error(request_id: str, error: Exception) -> None:
    logger.error(
        "firewall_error",
        extra={
            "extra": {
                "request_id": request_id,
                "error_type": type(error).__name__,
                "error":      str(error),
            }
        },
        exc_info=True,
    )
