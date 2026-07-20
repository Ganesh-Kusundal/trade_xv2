"""Order placement — equity resolution and OMS submission.

Extracted from ``TradingOrchestrator`` to separate order routing from
signal gating and event-publishing concerns.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from application.execution.execution_engine import ExecutionEngine
from application.oms.order_manager import OmsOrderCommand, OrderManager, OrderResult
from domain.models.trading import SignalDTO

logger = logging.getLogger(__name__)


class OrderPlacer:
    """Places orders through the execution spine.

    Responsibilities
    ----------------
    - Equity resolution for position sizing
    - Order submission via :class:`ExecutionEngine`

    Parameters
    ----------
    order_manager:
        OMS order manager (equity resolution via risk_manager).
    execution_engine:
        Unified execution engine — sole placement path.
    on_error:
        Optional callback invoked on placement failure (for counter bumps).
    """

    def __init__(
        self,
        order_manager: OrderManager,
        *,
        execution_engine: ExecutionEngine,
        on_error: Callable[[], None] | None = None,
    ) -> None:
        if execution_engine is None:
            raise TypeError("execution_engine is required")
        self._order_manager = order_manager
        self._execution_engine = execution_engine
        self._on_error = on_error

    # ── equity ───────────────────────────────────────────────────────────

    def resolve_equity(self) -> float:
        """Best-effort available capital for sizing."""
        # G7 (P5-8): no getattr reach-through. OrderManager exposes a public
        # `risk_manager` property; the capital provider is read directly.
        order_manager = self._order_manager
        if order_manager is None:
            return 0.0
        rm = order_manager.risk_manager
        if rm is None:
            return 0.0
        provider = rm.capital_provider
        if provider is None:
            return 0.0
        try:
            bal = provider.get_available_balance()
            return float(bal)
        except Exception:
            logger.exception("Failed to resolve equity for sizing")
            return 0.0

    # ── placement ────────────────────────────────────────────────────────

    def place(
        self,
        command: OmsOrderCommand,
        signal: SignalDTO,
    ) -> OrderResult:
        """Place *command* through the execution spine."""
        try:
            logger.info(
                "Placing order: %s %s %d @ %.2f (correlation=%s)",
                command.side.value,
                command.symbol,
                command.quantity,
                float(command.price),
                command.correlation_id,
            )

            return self._execution_engine.place_order(command)

        except Exception as exc:
            logger.exception("Order placement failed for %s: %s", command.symbol, exc)
            if self._on_error is not None:
                self._on_error()
            return OrderResult(success=False, error=str(exc))
