"""Centralized logging configuration with structured logging support.

Provides a single, consistent logging setup for the entire TradeXV2 platform.
Supports structured JSON logging for production and human-readable output for
development.

Token-leak protection (REF-29)
-------------------------------
The :class:`TokenRedactionFilter` installed by ``configure_logging``
redacts any substring that matches an access-token, refresh-token,
or API-key pattern. This is a defence-in-depth measure.

Usage:
    from infrastructure.logging_config import configure_logging, get_logger
    
    # Configure at application startup
    configure_logging(service="api", level="INFO")
    
    # Get a structured logger
    logger = get_logger(__name__)
    logger.info("Order placed", extra={"order_id": "123", "symbol": "RELIANCE"})
"""

from __future__ import annotations

import json
import logging
import logging.config
import os
import re
import sys
import threading
from datetime import datetime, timezone
from typing import Any

# Thread-local storage for context
_thread_local = threading.local()


def set_context(**kwargs: Any) -> None:
    """Set logging context for the current thread/async context."""
    if not hasattr(_thread_local, "context"):
        _thread_local.context = {}
    _thread_local.context.update(kwargs)


def clear_context() -> None:
    """Clear all logging context for the current thread."""
    _thread_local.context = {}


def get_context() -> dict[str, Any]:
    """Get current logging context."""
    return getattr(_thread_local, "context", {})


# Token redaction patterns (REF-29)
_TOKEN_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(access_token\s*=\s*)([^\s,;]+)", re.IGNORECASE),
    re.compile(r"(refresh_token\s*=\s*)([^\s,;]+)", re.IGNORECASE),
    re.compile(r"(api_key\s*=\s*)([^\s,;]+)", re.IGNORECASE),
    re.compile(r"(api_secret\s*=\s*)([^\s,;]+)", re.IGNORECASE),
    re.compile(r"(password\s*=\s*)([^\s,;]+)", re.IGNORECASE),
    re.compile(r"(authorization:\s*Bearer\s+)([^\s,;]+)", re.IGNORECASE),
    re.compile(r"([?&]token=)([^&\s\"']+)", re.IGNORECASE),
    re.compile(r"((?:DHAN|UPSTOX|ZERODHA|ANGEL)[A-Z_]*TOKEN\s*=\s*)([^\s,;]+)"),
    re.compile(r"\b([A-Za-z0-9_\-]{32,})\b"),
)

_SENSITIVE_EXTRA_KEYS: frozenset[str] = frozenset({
    "token", "access_token", "refresh_token", "api_key", "api_secret",
    "password", "pin", "totp", "totp_secret", "authorization", "bearer_token",
})


class TokenRedactionFilter(logging.Filter):
    """Redact token-like substrings from log records."""
    
    REDACTED = "<REDACTED>"
    
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
        except Exception:
            return True
        redacted = _redact(msg)
        if redacted != msg:
            record.msg = redacted
            record.args = ()
        _redact_record_extras(record)
        return True


def _redact_record_extras(record: logging.LogRecord) -> None:
    """Redact sensitive values in structured extra fields."""
    for key, value in list(record.__dict__.items()):
        if key in _LOG_RECORD_BUILTIN_KEYS:
            continue
        key_lower = key.lower()
        if key_lower in _SENSITIVE_EXTRA_KEYS or key_lower.endswith("_token"):
            if isinstance(value, str) and value:
                record.__dict__[key] = TokenRedactionFilter.REDACTED
            continue
        if isinstance(value, str) and value:
            record.__dict__[key] = _redact(value)


_LOG_RECORD_BUILTIN_KEYS = frozenset(logging.LogRecord("", 0, "", 0, "", (), None).__dict__)


def _redact(text: str) -> str:
    """Apply every token redaction pattern to text."""
    for pattern in _TOKEN_PATTERNS:
        text = pattern.sub(_replace, text)
    return text


def _replace(match: re.Match[str]) -> str:
    """Substitute captured group with REDACTED."""
    groups = match.groups()
    if len(groups) >= 2 and groups[-1] and groups[0]:
        return f"{groups[0]}{TokenRedactionFilter.REDACTED}"
    return TokenRedactionFilter.REDACTED


class StructuredFormatter(logging.Formatter):
    """JSON-structured log formatter for production use."""
    
    def __init__(self, service: str = "tradexv2") -> None:
        super().__init__()
        self._service = service
    
    def format(self, record: logging.LogRecord) -> str:
        log_entry: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "service": self._service,
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
            "thread": record.threadName,
            "process": record.process,
        }
        if record.exc_info and record.exc_info[0]:
            log_entry["exception"] = {
                "type": record.exc_info[0].__name__,
                "message": str(record.exc_info[1]),
            }
        context = get_context()
        if context:
            log_entry["context"] = context
        for key, value in record.__dict__.items():
            if key not in _LOG_RECORD_BUILTIN_KEYS:
                log_entry[key] = value
        return json.dumps(log_entry, default=str)


class HumanReadableFormatter(logging.Formatter):
    """Human-readable log formatter for development use."""
    
    COLORS = {
        "DEBUG": "\033[36m", "INFO": "\033[32m", "WARNING": "\033[33m",
        "ERROR": "\033[31m", "CRITICAL": "\033[41m",
    }
    RESET = "\033[0m"
    
    def format(self, record: logging.LogRecord) -> str:
        timestamp = datetime.fromtimestamp(record.created, tz=timezone.utc).strftime("%H:%M:%S.%f")[:-3]
        color = self.COLORS.get(record.levelname, "")
        level = f"{record.levelname:<8}"
        context = get_context()
        context_str = ""
        if context:
            context_str = " [" + " ".join(f"{k}={v}" for k, v in context.items()) + "]"
        message = record.getMessage()
        if record.exc_info and record.exc_info[0]:
            message += f" | {record.exc_info[0].__name__}: {record.exc_info[1]}"
        return f"{color}{timestamp}{self.RESET} {color}{level}{self.RESET} {record.name:<30} {message}{context_str}"


def configure_logging(
    service: str = "tradexv2",
    level: str | None = None,
    log_format: str | None = None,
    log_file: str | None = None,
    enable_redaction: bool = True,
) -> None:
    """Configure logging for the entire application.
    
    Args:
        service: Service name for log identification.
        level: Log level (DEBUG, INFO, WARNING, ERROR). Defaults to env var
            XV2_LOG_LEVEL or INFO.
        log_format: 'json' for structured, 'human' for readable. Defaults to
            'json' in production, 'human' otherwise.
        log_file: Optional file path for log output.
        enable_redaction: If True (default), install TokenRedactionFilter.
    """
    if level is None:
        level = os.environ.get("XV2_LOG_LEVEL", "INFO")
    level = level.upper()
    
    if log_format is None:
        is_production = os.environ.get("APP_ENV", "").lower() in ("prod", "production")
        log_format = "json" if is_production else "human"
    
    if log_format == "json":
        formatter = StructuredFormatter(service=service)
    else:
        formatter = HumanReadableFormatter()
    
    handlers: dict[str, Any] = {
        "console": {
            "class": "logging.StreamHandler",
            "stream": sys.stdout,
            "formatter": "standard",
        }
    }
    if enable_redaction:
        handlers["console"]["filters"] = ["token_redaction"]
    
    if log_file:
        handlers["file"] = {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": log_file,
            "maxBytes": 10 * 1024 * 1024,
            "backupCount": 5,
            "formatter": "standard",
        }
        if enable_redaction:
            handlers["file"]["filters"] = ["token_redaction"]
    
    config: dict[str, Any] = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {"standard": {"()": lambda: formatter}},
        "filters": (
            {"token_redaction": {"()": "infrastructure.logging_config.TokenRedactionFilter"}}
            if enable_redaction else {}
        ),
        "handlers": handlers,
        "root": {"level": level, "handlers": list(handlers.keys())},
        "loggers": {
            "urllib3": {"level": "WARNING", "handlers": list(handlers.keys())},
            "httpx": {"level": "WARNING", "handlers": list(handlers.keys())},
            "websockets": {"level": "WARNING", "handlers": list(handlers.keys())},
            "asyncio": {"level": "WARNING", "handlers": list(handlers.keys())},
        },
    }
    
    logging.config.dictConfig(config)
    
    logger = logging.getLogger(__name__)
    logger.info(
        "Logging configured",
        extra={"service": service, "level": level, "format": log_format, "log_file": log_file},
    )


def get_logger(name: str) -> logging.Logger:
    """Get a structured logger instance."""
    return logging.getLogger(name)


__all__ = [
    "configure_logging",
    "get_logger",
    "set_context",
    "clear_context",
    "get_context",
    "TokenRedactionFilter",
    "StructuredFormatter",
    "HumanReadableFormatter",
]