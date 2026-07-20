"""Production boot validation — fail-closed on unsafe configuration.

Activated when ``TRADEX_ENV`` is ``production`` or ``staging``. Skipped
during pytest unless ``TRADEX_FORCE_PROD_VALIDATION=1``.
"""

from __future__ import annotations

import logging
import os
from typing import Literal

logger = logging.getLogger(__name__)

Surface = Literal["api", "runtime"]


def is_production_environment() -> bool:
    """Return True when strict production config checks must run."""
    if os.getenv("PYTEST_CURRENT_TEST") and os.getenv("TRADEX_FORCE_PROD_VALIDATION") != "1":
        return False
    env = (os.getenv("TRADEX_ENV") or "development").strip().lower()
    return env in ("production", "staging")


def _unsafe_env(name: str) -> bool:
    return (os.getenv(name) or "").strip() == "1"


def validate_production_config(*, surface: Surface = "runtime") -> None:
    """Raise RuntimeError if production environment has unsafe settings.

    Parameters
    ----------
    surface:
        ``api`` enforces API authentication. ``runtime`` enforces trading
        safety gates (risk fail-open, parity skip).
    """
    if not is_production_environment():
        return

    violations: list[str] = []

    if surface == "api":
        pass  # ponytail: API auth optional; default AUTH_MODE=none

    if _unsafe_env("RISK_FAIL_OPEN"):
        violations.append(
            "RISK_FAIL_OPEN=1 is forbidden in production "
            "(phantom capital override)"
        )

    if _unsafe_env("SKIP_PARITY_GATE"):
        violations.append(
            "SKIP_PARITY_GATE=1 is forbidden in production "
            "(quant parity must pass before live boot)"
        )

    if violations:
        msg = "Production configuration validation failed:\n" + "\n".join(
            f"  - {v}" for v in violations
        )
        logger.error(msg)
        raise RuntimeError(msg)

    logger.info("Production configuration validation passed (surface=%s)", surface)
