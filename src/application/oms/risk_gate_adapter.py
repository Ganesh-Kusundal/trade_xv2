"""Adapter: domain RiskGate → OMS risk-check interface.

The domain ``RiskGate`` (``domain.risk.policy``) accepts decimal values
(order_notional, portfolio_notional, total_exposure, capital).  The OMS
``OrderValidator`` expects a ``check_order(order) -> RiskResult`` callable.

This adapter bridges the two: it extracts notional information from the
``Order`` entity and delegates to the ``RiskGate``.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from application.oms._internal.risk_types import RiskResult
from domain.risk.policy import RiskGate as DomainRiskGate

logger = logging.getLogger(__name__)


@dataclass
class RiskGateAdapter:
    """Thin adapter that makes ``RiskGate`` satisfy the OMS risk-check interface.

    Parameters
    ----------
    gate:
        A ``domain.risk.policy.RiskGate`` instance (or any object with a
        ``check_order`` method accepting four ``Decimal`` parameters).
    capital_fn:
        A callable returning current available capital as ``Decimal``.
    portfolio_notional_fn:
        A callable returning current portfolio notional as ``Decimal``.
    total_exposure_fn:
        A callable returning total portfolio exposure as ``Decimal``.
    """

    gate: DomainRiskGate
    capital_fn: Callable[[], Decimal] | None = None
    portfolio_notional_fn: Callable[[], Decimal] | None = None
    total_exposure_fn: Callable[[], Decimal] | None = None

    def check_order(self, order: Any) -> RiskResult:
        """Check order against the domain RiskGate.

        Extracts order notional from the Order entity and delegates to
        ``RiskGate.check_order``.
        """
        order_notional = self._extract_notional(order)
        capital = self._call_fn(self.capital_fn, Decimal("100000"))
        portfolio_notional = self._call_fn(self.portfolio_notional_fn, Decimal("0"))
        total_exposure = self._call_fn(self.total_exposure_fn, Decimal("0"))

        result = self.gate.check_order(
            order_notional=order_notional,
            portfolio_notional=portfolio_notional,
            total_exposure=total_exposure,
            capital=capital,
        )
        return RiskResult(allowed=result.approved, reason=result.reason or None)

    def _extract_notional(self, order: Any) -> Decimal:
        """Best-effort notional extraction from an Order entity."""
        price = getattr(order, "price", None)
        quantity = getattr(order, "quantity", 0)
        if price is not None and quantity:
            return Decimal(str(price)) * Decimal(str(quantity))
        if price is None:
            logger.warning(
                "RiskGateAdapter: order %s has no price — notional is zero. "
                "Risk check may be bypassed.",
                getattr(order, "order_id", "?"),
            )
        return Decimal("0")

    @staticmethod
    def _call_fn(fn: Callable[[], Decimal] | None, default: Decimal) -> Decimal:
        """Call fn() and return result, or default if fn is None."""
        if fn is None:
            return default
        try:
            result = fn()
            return Decimal(str(result)) if result is not None else default
        except Exception as exc:
            logger.debug("RiskGateAdapter._call_fn failed: %s", exc)
            return default
