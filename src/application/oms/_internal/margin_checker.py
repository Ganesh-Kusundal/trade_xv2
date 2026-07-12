"""F&O margin checking and pending-exposure bookkeeping.

Extracted from :class:`~application.oms._internal.risk_manager.RiskManager`.
Owns:

* the derivative margin check (fail-closed),
* the pending-exposure reservations between risk check and terminal order
  state, and
* best-effort market-context resolution (LTP / ref price / multiplier) used
  for notional sizing upstream in :meth:`RiskManager.check_order`.

This module must NOT import from ``risk_manager`` (no circular deps).
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any

from domain import Order
from domain.constants.market import DEFAULT_TICK_SIZE
from domain.exchange_segments import is_derivative_segment
from domain.ports.margin_provider import MarginProviderPort
from domain.value_objects.price import is_tick_aligned

from application.oms._internal.risk_types import (
    InstrumentProvider,
    RiskConfig,
    RiskResult,
)

logger = logging.getLogger(__name__)


class MarginChecker:
    """Derivative margin check + pending-exposure tracking.

    Stateless with respect to portfolio/capital; it only consults the
    (optional) margin provider and tracks the notional reservations made by
    :meth:`RiskManager.check_order` until the order reaches a terminal state.
    """

    def __init__(
        self,
        config: RiskConfig,
        margin_provider: MarginProviderPort | None = None,
        instrument_provider: InstrumentProvider | None = None,
    ) -> None:
        self._config = config
        self._margin_provider = margin_provider
        self._instrument_provider = instrument_provider
        # Pending exposure reserved between risk check and terminal order state.
        self._pending_by_correlation: dict[str, Decimal] = {}
        self._pending_meta: dict[str, tuple[str, str]] = {}

    # -- Pending exposure (delegated from RiskManager) --

    def release_pending(self, correlation_id: str | None) -> None:
        """Release a pending exposure reservation (idempotent)."""
        if not correlation_id:
            return
        self._pending_by_correlation.pop(correlation_id, None)
        self._pending_meta.pop(correlation_id, None)

    def reserve_pending(self, order: Order, notional: Decimal) -> None:
        """Record a pending exposure reservation for ``order``."""
        if order.correlation_id:
            self._pending_by_correlation[order.correlation_id] = notional
            self._pending_meta[order.correlation_id] = (order.symbol, order.exchange)

    def pending_gross(self) -> Decimal:
        return sum(self._pending_by_correlation.values(), Decimal("0"))

    def pending_symbol_notional(self, symbol: str, exchange: str) -> Decimal:
        total = Decimal("0")
        for cid, (sym, ex) in self._pending_meta.items():
            if sym == symbol and ex == exchange:
                total += self._pending_by_correlation.get(cid, Decimal("0"))
        return total

    # -- Market context (delegated from RiskManager) --

    def resolve_market_context(
        self, order: Order
    ) -> tuple[Decimal | None, Decimal | None, Any | None]:
        """Best-effort LTP/ref price and multiplier for notional sizing.

        Priority for ref price: order.price (handled by effective_notional),
        then open position LTP, then instrument last/ltp attributes.
        """
        ref: Decimal | None = None
        mult: Decimal | None = None
        instrument: Any | None = None

        if self._instrument_provider is not None:
            try:
                instrument = self._instrument_provider.resolve(order.symbol, order.exchange)
            except Exception as exc:
                logger.warning(
                    "notional_instrument_lookup_failed",
                    extra={
                        "symbol": order.symbol,
                        "exchange": order.exchange,
                        "error": str(exc),
                    },
                )
                instrument = None
            if instrument is not None:
                for attr in ("ltp", "last_price", "last_traded_price"):
                    raw = getattr(instrument, attr, None)
                    if raw is not None:
                        try:
                            cand = Decimal(str(raw))
                            if cand > 0:
                                ref = cand
                                break
                        except Exception:
                            pass
                raw_m = getattr(instrument, "multiplier", None)
                if raw_m is not None:
                    try:
                        m = Decimal(str(raw_m))
                        if m > 0:
                            mult = m
                    except Exception:
                        pass

        return ref, mult, instrument

    # -- Margin check (B3) --

    def check(self, order: Order) -> RiskResult:
        """Check margin requirement for derivative orders.

        Fail-closed design: if margin provider is unavailable or the API
        call fails, the order is rejected. This is safer than allowing an
        unvalidated F&O order through to the broker.

        Args:
            order: The order to validate.

        Returns:
            RiskResult indicating whether the margin check passed.
        """
        if self._margin_provider is None:
            logger.warning(
                "margin_check_no_provider",
                extra={
                    "symbol": order.symbol,
                    "exchange": order.exchange,
                    "quantity": order.quantity,
                },
            )
            return RiskResult(False, "F&O order rejected: no margin provider configured")

        try:
            margin_result = self._margin_provider.calculate_margin_for_order(
                symbol=order.symbol,
                exchange=order.exchange,
                quantity=order.quantity,
                price=order.price,
                product_type=order.product_type.value
                if hasattr(order.product_type, "value")
                else str(order.product_type),
                order_type=order.order_type.value
                if hasattr(order.order_type, "value")
                else str(order.order_type),
            )
        except Exception as exc:
            # Fail-closed: any unexpected error -> reject order
            logger.error(
                "margin_check_error",
                extra={
                    "symbol": order.symbol,
                    "exchange": order.exchange,
                    "error": str(exc),
                },
            )
            return RiskResult(False, f"F&O order rejected: margin check error: {exc}")

        required_with_buffer = margin_result.required_margin * self._config.margin_safety_multiplier

        # Check if available margin covers the REQUIRED margin WITH the safety buffer
        if margin_result.available_margin < required_with_buffer:
            logger.warning(
                "margin_check_insufficient",
                extra={
                    "symbol": order.symbol,
                    "exchange": order.exchange,
                    "required_margin": str(margin_result.required_margin),
                    "required_with_buffer": str(required_with_buffer),
                    "available_margin": str(margin_result.available_margin),
                },
            )
            return RiskResult(
                False,
                f"Insufficient margin for {order.symbol}: "
                f"required={margin_result.required_margin} "
                f"(with buffer: {required_with_buffer}), "
                f"available={margin_result.available_margin}",
            )

        logger.info(
            "margin_check_passed",
            extra={
                "symbol": order.symbol,
                "exchange": order.exchange,
                "required_margin": str(margin_result.required_margin),
                "available_margin": str(margin_result.available_margin),
            },
        )
        return RiskResult(True)
