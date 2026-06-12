"""Structured JSON logging for operation observability."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone


class StructuredLogger:
    """Logger that emits structured JSON log records."""

    def __init__(self, name: str) -> None:
        self._logger = logging.getLogger(name)

    def info(self, event: str, **fields: object) -> None:
        """Log an informational event as JSON.

        Args:
            event: Name or description of the event.
            **fields: Additional key-value pairs to include in the log record.
        """
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": "INFO",
            "event": event,
            **fields,
        }
        self._logger.info(json.dumps(record))

    def error(self, event: str, error: Exception, **fields: object) -> None:
        """Log an error event as JSON.

        Args:
            event: Name or description of the event.
            error: The exception that occurred.
            **fields: Additional key-value pairs to include in the log record.
        """
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": "ERROR",
            "event": event,
            "error_type": type(error).__name__,
            "error_message": str(error),
            **fields,
        }
        self._logger.error(json.dumps(record))

    def warning(self, event: str, **fields: object) -> None:
        """Log a warning event as JSON.

        Args:
            event: Name or description of the event.
            **fields: Additional key-value pairs to include in the log record.
        """
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": "WARNING",
            "event": event,
            **fields,
        }
        self._logger.warning(json.dumps(record))
