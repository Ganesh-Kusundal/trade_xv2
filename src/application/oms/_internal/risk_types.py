"""Shared risk types for the OMS risk pipeline.

Extracted from :mod:`application.oms._internal.risk_manager` so the
decomposed risk modules (margin checker, kill switch, daily-PnL tracker)
can depend on these without creating a circular import back to
``risk_manager``. This module must NOT import from ``risk_manager``.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from domain.constants import (
    RISK_DAILY_LOSS_PERCENT,
    RISK_GROSS_PERCENT,
    RISK_MARGIN_SAFETY_MULTIPLIER,
    RISK_POSITION_PERCENT,
)

if TYPE_CHECKING:
    from domain.risk.policy import RiskResult as DomainRiskResult

logger = __import__("logging").getLogger(__name__)


@runtime_checkable
class InstrumentProvider(Protocol):
    """Narrow protocol for instrument lookups (tick size, lot size, etc.)."""

    def resolve(self, symbol: str, exchange: str) -> Any: ...


@dataclass(frozen=True)
class RiskConfig:
    max_daily_loss_pct: Decimal = Decimal(str(RISK_DAILY_LOSS_PERCENT))  # of capital
    max_position_pct: Decimal = Decimal(str(RISK_POSITION_PERCENT))  # of capital per symbol
    max_gross_exposure_pct: Decimal = Decimal(str(RISK_GROSS_PERCENT))  # of capital
    kill_switch: bool = False
    margin_safety_multiplier: Decimal = Decimal(str(RISK_MARGIN_SAFETY_MULTIPLIER))
    enable_margin_check: bool = True

    def replace(self, **changes: Any) -> "RiskConfig":
        """Convenience mirror of :func:`dataclasses.replace` for callers."""
        return replace(self, **changes)


@dataclass(frozen=True)
class RiskResult:
    allowed: bool
    reason: str | None = None


def risk_result_from_domain(domain_result: "DomainRiskResult") -> RiskResult:
    """Map ``domain.risk.policy.RiskResult`` (``approved``) → OMS ``RiskResult`` (``allowed``).

    Bridge only — does not reimplement domain policy. Callers that already hold a
    domain :class:`~domain.risk.policy.RiskResult` (e.g. from :class:`~domain.risk.policy.KillSwitch`)
    use this to stay on the OMS ``check_order`` return type.
    """
    return RiskResult(
        allowed=domain_result.approved,
        reason=domain_result.reason or None,
    )
