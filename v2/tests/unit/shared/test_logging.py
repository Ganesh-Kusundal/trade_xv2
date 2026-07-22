"""Structured logging setup."""

import structlog

from shared.logging.setup import setup_logging


def test_setup_logging_does_not_crash() -> None:
    setup_logging(level="INFO", json_output=False)
    log = structlog.get_logger("test")
    assert log is not None
    log.info("smoke")
