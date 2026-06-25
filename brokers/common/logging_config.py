"""Central logging configuration for TradeXV2.

Replaces scattered basicConfig() calls with a single dictConfig.
Called once from cli/main.py before any other imports that log.

Usage::

    from brokers.common.logging_config import setup_logging
    setup_logging(log_level="DEBUG")  # or from env XV2_LOG_LEVEL

Token-leak protection (REF-29)
------------------------------
The :class:`TokenRedactionFilter` installed by ``setup_logging``
redacts any substring that matches an access-token, refresh-token,
or API-key pattern. This is a defence-in-depth measure: even if a
caller accidentally formats a credential into a log message (e.g.
``logger.info("token=%s", token)``), the logger will emit
``token=<REDACTED>`` instead.

Patterns redacted:

- ``access_token=<value>``
- ``refresh_token=<value>``
- ``api_key=<value>``
- ``authorization: Bearer <value>``
- ``?token=<value>`` / ``&token=<value>`` (WebSocket URL query params)
- ``DHAN_ACCESS_TOKEN=<value>``
- ``UPSTOX_ACCESS_TOKEN=<value>``
- Any standalone 32+ char base64url-looking substring (heuristic)

The filter is NOT a substitute for code review. Loggers are an
untrusted sink: prefer explicit ``extra={"client_id": ...}`` (no
secrets) over format strings.
"""

from __future__ import annotations

import logging
import os
import re
from logging.config import dictConfig
from pathlib import Path
from typing import Any

_initialized = False


# Patterns matched against the formatted log message. The order
# matters — more specific patterns first. Each pattern MUST capture
# only the secret portion; the redaction replaces the captured group
# with ``<REDACTED>``.
_TOKEN_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(access_token\s*=\s*)([^\s,;]+)", re.IGNORECASE),
    re.compile(r"(refresh_token\s*=\s*)([^\s,;]+)", re.IGNORECASE),
    re.compile(r"(api_key\s*=\s*)([^\s,;]+)", re.IGNORECASE),
    re.compile(r"(api_secret\s*=\s*)([^\s,;]+)", re.IGNORECASE),
    re.compile(r"(password\s*=\s*)([^\s,;]+)", re.IGNORECASE),
    re.compile(r"(authorization:\s*Bearer\s+)([^\s,;]+)", re.IGNORECASE),
    # WebSocket / HTTP query-string tokens (e.g. ?token=eyJ...)
    re.compile(r"([?&]token=)([^&\s\"']+)", re.IGNORECASE),
    # Environment-variable style: DHAN_ACCESS_TOKEN=abc123
    re.compile(r"((?:DHAN|UPSTOX|ZERODHA|ANGEL)[A-Z_]*TOKEN\s*=\s*)([^\s,;]+)"),
    # 32+ char base64url-style tokens (very loose heuristic; catches
    # things like ``eyJhbGciOi...`` JWT prefixes).
    re.compile(r"\b([A-Za-z0-9_\-]{32,})\b"),
)


_SENSITIVE_EXTRA_KEYS: frozenset[str] = frozenset(
    {
        "token",
        "access_token",
        "refresh_token",
        "api_key",
        "api_secret",
        "password",
        "pin",
        "totp",
        "totp_secret",
        "authorization",
        "bearer_token",
    }
)


class TokenRedactionFilter(logging.Filter):
    """Redact token-like substrings from log records.

    The filter runs in :meth:`filter` for every record before it is
    emitted by the handler. It modifies ``record.msg`` and
    ``record.args`` *in place* so that downstream formatters see the
    redacted text. This is necessary because :class:`logging.LogRecord`
    freezes the message at construction time, so a naive filter that
    returns a new message would not reach the formatter.

    The filter is intentionally conservative: false positives (e.g.
    a 32-char hex hash) get redacted rather than leaked. The cost is
    a few extra ``<REDACTED>`` strings in logs; the benefit is that
    a single careless ``logger.info(f"token={t}")`` cannot leak.
    """

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
    """Redact sensitive values in structured ``extra`` fields."""
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
    """Apply every pattern in :data:`_TOKEN_PATTERNS` to ``text``."""
    for pattern in _TOKEN_PATTERNS:
        text = pattern.sub(_replace, text)
    return text


def _replace(match: re.Match[str]) -> str:
    """Substitute the captured group with ``<REDACTED>``.

    For multi-group patterns, only the secret-bearing group is
    replaced; the prefix (``access_token=``) is preserved.
    """
    groups = match.groups()
    if len(groups) >= 2 and groups[-1] and groups[0]:
        return f"{groups[0]}{TokenRedactionFilter.REDACTED}"
    # Fallback: redact the entire match.
    return TokenRedactionFilter.REDACTED


def setup_logging(
    log_level: str | None = None,
    log_file: Path | str | None = None,
    json_format: bool = False,
    enable_redaction: bool = True,
) -> None:
    """Configure application-wide logging.

    Args:
        log_level: Root logger level (default: XV2_LOG_LEVEL env var or INFO).
        log_file: Optional file path for FileHandler.
        json_format: If True, use JSON formatter (requires python-json-logger).
        enable_redaction: If True (default), install
            :class:`TokenRedactionFilter` on every handler. Disable
            only for debugging.
    """
    global _initialized
    if _initialized:
        return

    level = log_level or os.environ.get("XV2_LOG_LEVEL", "INFO").upper()

    redaction_filter: dict[str, Any] | None = (
        {"()": "brokers.common.logging_config.TokenRedactionFilter"} if enable_redaction else None
    )

    console_handler: dict[str, Any] = {
        "class": "logging.StreamHandler",
        "level": level,
        "formatter": "standard",
        "stream": "ext://sys.stderr",
    }
    if redaction_filter is not None:
        console_handler["filters"] = ["token_redaction"]

    config: dict[str, Any] = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "standard": {
                "format": "%(asctime)s %(name)s %(levelname)s %(message)s",
                "datefmt": "%Y-%m-%d %H:%M:%S",
            },
        },
        "filters": (
            {"token_redaction": {"()": "brokers.common.logging_config.TokenRedactionFilter"}}
            if redaction_filter is not None
            else {}
        ),
        "handlers": {
            "console": console_handler,
        },
        "root": {
            "level": level,
            "handlers": ["console"],
        },
        "loggers": {
            # Silence noisy third-party libraries
            "urllib3": {"level": "WARNING", "handlers": ["console"], "propagate": False},
            "websockets": {"level": "WARNING", "handlers": ["console"], "propagate": False},
            "aiohttp": {"level": "WARNING", "handlers": ["console"], "propagate": False},
            "requests": {"level": "WARNING", "handlers": ["console"], "propagate": False},
        },
    }

    # Add JSON formatter if requested
    if json_format:
        try:
            config["formatters"]["json"] = {
                "()": "pythonjsonlogger.jsonlogger.JsonFormatter",
                "fmt": "%(asctime)s %(name)s %(levelname)s %(message)s",
            }
            config["handlers"]["console"]["formatter"] = "json"
        except ImportError:
            # python-json-logger not installed, fall back to standard
            pass

    # Add file handler if requested
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler: dict[str, Any] = {
            "class": "logging.FileHandler",
            "level": level,
            "formatter": "standard",
            "filename": str(log_path),
        }
        if redaction_filter is not None:
            file_handler["filters"] = ["token_redaction"]
        config["handlers"]["file"] = file_handler
        config["root"]["handlers"].append("file")

    dictConfig(config)
    _initialized = True

    # Log initialization
    logging.getLogger(__name__).info(
        "logging_initialized",
        extra={"level": level, "file": str(log_file) if log_file else None},
    )
