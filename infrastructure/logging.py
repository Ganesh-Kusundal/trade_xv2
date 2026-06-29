"""Structured logging infrastructure with automatic correlation ID injection.

P5 Stability Engineering: Every log message carries end-to-end correlation
ID for distributed tracing, enabling production debugging across async
event handlers, order lifecycle, and broker integrations.

Usage:
    from infrastructure.logging import get_logger
    
    logger = get_logger(__name__)
    logger.info("Order placed", extra={"order_id": "O1"})
"""

from __future__ import annotations

import json
import logging
import os
import sys
import threading
from datetime import datetime, timezone
from logging import LogRecord
from typing import Any


class CorrelationFilter(logging.Filter):
    """Logging filter that injects correlation_id into every log record."""

    def __init__(self) -> None:
        super().__init__()
        self._service_name = os.getenv("TRADING_SERVICE_NAME", "trading-platform")

    def filter(self, record: LogRecord) -> bool:
        """Inject correlation_id and service_name into log record."""
        from infrastructure.correlation import get_current_correlation_id

        record.correlation_id = get_current_correlation_id() or "no-correlation"
        record.service_name = self._service_name
        return True


class JSONFormatter(logging.Formatter):
    """JSON log formatter for production environments."""

    def format(self, record: LogRecord) -> str:
        """Format log record as JSON string."""
        log_data: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "correlation_id": getattr(record, "correlation_id", "no-correlation"),
            "service_name": getattr(record, "service_name", "unknown"),
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        if record.exc_info and record.exc_info[0] is not None:
            log_data["exception"] = {
                "type": record.exc_info[0].__name__,
                "message": str(record.exc_info[1]),
                "traceback": self.formatException(record.exc_info),
            }

        standard_attrs = {
            "name", "msg", "args", "created", "relativeCreated",
            "exc_info", "exc_text", "stack_info", "lineno", "funcName",
            "pathname", "filename", "module", "thread", "threadName",
            "processName", "process", "message", "levelno", "levelname",
            "correlation_id", "service_name",
        }

        for key, value in record.__dict__.items():
            if key not in standard_attrs and not key.startswith("_"):
                try:
                    json.dumps(value)
                    log_data[key] = value
                except (TypeError, ValueError):
                    log_data[key] = str(value)

        return json.dumps(log_data)


class ConsoleFormatter(logging.Formatter):
    """Human-readable console formatter for development."""

    def format(self, record: LogRecord) -> str:
        """Format log record as human-readable string."""
        timestamp = datetime.fromtimestamp(record.created, tz=timezone.utc).strftime(
            "%Y-%m-%d %H:%M:%S"
        )

        correlation_id = getattr(record, "correlation_id", "no-correlation")
        message = record.getMessage()

        standard_attrs = {
            "name", "msg", "args", "created", "relativeCreated",
            "exc_info", "exc_text", "stack_info", "lineno", "funcName",
            "pathname", "filename", "module", "thread", "threadName",
            "processName", "process", "message", "levelno", "levelname",
            "correlation_id", "service_name",
        }

        extra_parts = []
        for key, value in record.__dict__.items():
            if key not in standard_attrs and not key.startswith("_"):
                extra_parts.append(f"{key}={value}")

        extra_str = " ".join(extra_parts)
        log_line = f"{timestamp} {record.levelname:<7} [{correlation_id}] {message}"
        if extra_str:
            log_line += f" - {extra_str}"

        if record.exc_info and record.exc_info[0] is not None:
            log_line += f"\n{self.formatException(record.exc_info)}"

        return log_line


_is_production = os.getenv("TRADING_ENV", "development").lower() == "production"
_lock = threading.Lock()
_initialized = False


def _initialize_root_logger() -> None:
    """Initialize root logger with structured formatting (idempotent)."""
    global _initialized

    if _initialized:
        return

    with _lock:
        if _initialized:
            return

        root_logger = logging.getLogger()
        root_logger.setLevel(logging.DEBUG)
        root_logger.handlers.clear()

        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(logging.DEBUG)

        correlation_filter = CorrelationFilter()
        handler.addFilter(correlation_filter)

        if _is_production:
            handler.setFormatter(JSONFormatter())
        else:
            handler.setFormatter(ConsoleFormatter())

        root_logger.addHandler(handler)
        _initialized = True


def get_logger(name: str) -> logging.Logger:
    """Get a logger with automatic correlation ID injection."""
    _initialize_root_logger()
    return logging.getLogger(name)


def set_production_mode(enabled: bool) -> None:
    """Override production mode detection (for testing)."""
    global _is_production
    _is_production = enabled


__all__ = [
    "ConsoleFormatter",
    "CorrelationFilter",
    "JSONFormatter",
    "get_logger",
    "set_production_mode",
]
