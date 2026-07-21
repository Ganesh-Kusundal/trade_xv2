"""Logging and instrumentation constants (REF-13)."""

from __future__ import annotations

#: Default log level used by :func:`brokers.common.logging_config.setup_logging`.
DEFAULT_LOG_LEVEL: str = "INFO"

#: Default log level for noisy third-party loggers.
THIRD_PARTY_LOG_LEVEL: str = "WARNING"

__all__ = [
    "DEFAULT_LOG_LEVEL",
    "THIRD_PARTY_LOG_LEVEL",
]
