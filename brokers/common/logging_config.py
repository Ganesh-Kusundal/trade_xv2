"""Central logging configuration for TradeXV2.

Replaces scattered basicConfig() calls with a single dictConfig.
Called once from cli/main.py before any other imports that log.

Usage::

    from brokers.common.logging_config import setup_logging
    setup_logging(log_level="DEBUG")  # or from env XV2_LOG_LEVEL
"""

from __future__ import annotations

import logging
import os
import sys
from logging.config import dictConfig
from pathlib import Path
from typing import Any

_initialized = False


def setup_logging(
    log_level: str | None = None,
    log_file: Path | str | None = None,
    json_format: bool = False,
) -> None:
    """Configure application-wide logging.

    Args:
        log_level: Root logger level (default: XV2_LOG_LEVEL env var or INFO).
        log_file: Optional file path for FileHandler.
        json_format: If True, use JSON formatter (requires python-json-logger).
    """
    global _initialized
    if _initialized:
        return

    level = log_level or os.environ.get("XV2_LOG_LEVEL", "INFO").upper()

    config: dict[str, Any] = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "standard": {
                "format": "%(asctime)s %(name)s %(levelname)s %(message)s",
                "datefmt": "%Y-%m-%d %H:%M:%S",
            },
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "level": level,
                "formatter": "standard",
                "stream": "ext://sys.stderr",
            },
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
        config["handlers"]["file"] = {
            "class": "logging.FileHandler",
            "level": level,
            "formatter": "standard",
            "filename": str(log_path),
        }
        config["root"]["handlers"].append("file")

    dictConfig(config)
    _initialized = True

    # Log initialization
    logging.getLogger(__name__).info(
        "logging_initialized",
        extra={"level": level, "file": str(log_file) if log_file else None},
    )
