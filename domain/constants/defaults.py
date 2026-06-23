"""Named constants for domain-critical default values.

Previously these were hardcoded magic numbers scattered across the codebase
(``Decimal("100000")``, ``Decimal("10000")``, etc.). Centralising them here
gives them names, makes them configurable via environment overrides, and
provides a single grep target for audit.

Usage::

    from domain.constants.defaults import PAPER_INITIAL_CAPITAL, RISK_FALLBACK_CAPITAL
"""

from __future__ import annotations

import os
from decimal import Decimal


def _env_decimal(name: str, default: str) -> Decimal:
    """Read a Decimal from the environment or return *default*."""
    raw = os.environ.get(name, "")
    if raw:
        try:
            return Decimal(raw)
        except Exception:
            return Decimal(default)
    return Decimal(default)


# ── Risk / capital ──────────────────────────────────────────────────────────

RISK_FALLBACK_CAPITAL: Decimal = _env_decimal(
    "RISK_FALLBACK_CAPITAL", "100000"
)
"""Capital returned by :class:`GatewayCapitalProvider` when the gateway is
unavailable or ``funds()`` fails.  Prevents silent zero-capital risk checks."""

RISK_FAIL_OPEN_THRESHOLD: Decimal = _env_decimal(
    "RISK_FAIL_OPEN_THRESHOLD", "1000000"
)
"""Legacy placeholder used when ``RISK_FAIL_OPEN=1`` is set.  
Deprecated; production deployments should use ``RISK_FALLBACK_CAPITAL``."""


# ── Paper trading ───────────────────────────────────────────────────────────

PAPER_INITIAL_CAPITAL: Decimal = _env_decimal(
    "PAPER_INITIAL_CAPITAL", "1000000"
)
"""Default initial capital for :class:`~brokers.paper.PaperGateway`."""

PAPER_MAX_POSITION_PCT: Decimal = _env_decimal(
    "PAPER_MAX_POSITION_PCT", "10000"
)
"""Default max position / gross exposure / daily loss percentages for
the unrestricted paper-trading risk config."""


# ── Synthetic data generation (PaperGateway history) ────────────────────────

SYNTHETIC_BASE_PRICE_MIN: float = 500.0
SYNTHETIC_BASE_PRICE_RANGE: float = 4500.0
SYNTHETIC_DAILY_VOLATILITY: float = 0.02
"""Parameters for the deterministic random-walk price generator in
:meth:`PaperGateway.history`.  These produce reproducible synthetic OHLCV
data seeded from the symbol name hash."""


# ── Default timeframes / lookbacks ──────────────────────────────────────────

DEFAULT_LOOKBACK_DAYS: int = 90
DEFAULT_TIMEFRAME: str = "1D"
DEFAULT_EXCHANGE: str = "NSE"
DEFAULT_DERIVATIVES_EXCHANGE: str = "NFO"
"""Canonical defaults used in 15+ method signatures across the codebase."""
