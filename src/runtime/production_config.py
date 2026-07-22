"""Production boot validation — fail-closed on unsafe configuration.

Activated when ``AppConfig`` reports production/staging (``TRADEX_ENV`` or
``app_env``). Skipped during pytest unless ``TRADEX_FORCE_PROD_VALIDATION=1``.
"""

from __future__ import annotations

import logging
import os
from typing import Literal

from config.schema import AppConfig

logger = logging.getLogger(__name__)

Surface = Literal["api", "runtime"]


def is_production_environment() -> bool:
    """Return True when strict production config checks must run."""
    if os.getenv("PYTEST_CURRENT_TEST") and os.getenv("TRADEX_FORCE_PROD_VALIDATION") != "1":
        return False
    return AppConfig.from_env().is_production_or_staging()


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

    cfg = AppConfig.from_env()
    violations: list[str] = []

    if surface == "api":
        if cfg.auth_mode != "api_key":
            violations.append(
                f"AUTH_MODE must be 'api_key' in production/staging (got '{cfg.auth_mode}')"
            )
        if not cfg.api_key.strip():
            violations.append(
                "API_KEY must be set explicitly in production/staging "
                "(do not rely on auto-generated keys)"
            )

    if cfg.risk_fail_open:
        violations.append(
            "RISK_FAIL_OPEN=1 is forbidden in production "
            "(phantom capital override)"
        )

    if cfg.skip_parity_gate:
        violations.append(
            "SKIP_PARITY_GATE=1 is forbidden in production "
            "(quant parity must pass before live boot)"
        )

    if surface == "runtime":
        from runtime.execution_config import (
            assert_live_lift_preconditions,
            requested_live_execution_target,
        )

        if requested_live_execution_target():
            try:
                assert_live_lift_preconditions()
            except RuntimeError as exc:
                violations.append(str(exc).replace("\n", " "))

    if violations:
        msg = "Production configuration validation failed:\n" + "\n".join(
            f"  - {v}" for v in violations
        )
        logger.error(msg)
        raise RuntimeError(msg)

    logger.info("Production configuration validation passed (surface=%s)", surface)
