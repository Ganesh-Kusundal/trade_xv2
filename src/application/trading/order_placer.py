"""Order placement — equity resolution and OMS submission.

Extracted from ``TradingOrchestrator`` to separate order routing from
signal gating and event-publishing concerns.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from application.execution.execution_engine import ExecutionEngine
from application.execution.place_order_use_case import PlaceOrderUseCase
from application.oms.order_manager import OmsOrderCommand, OrderManager, OrderResult
from domain.models.trading import SignalDTO

logger = logging.getLogger(__name__)


class OrderPlacer:
    """Places orders through the OMS with fallback routing.

    Responsibilities
    ----------------
    - Equity resolution for position sizing
    - Order submission via ``order_command_fn`` / :class:`ExecutionEngine` /
      :class:`PlaceOrderUseCase`

    The three-tier fallback chain mirrors the original orchestrator behaviour:

    1. ``order_command_fn`` (ADR-012 CommandDispatcher path) when wired —
       **must** be OMS-backed (``OrderManager.place_order`` via
       ``runtime.commands.build_order_dispatcher``). Never a raw broker call.
    2. ``execution_engine`` when available.
    3. :class:`PlaceOrderUseCase` as the last resort (never bare OMS).

    Parameters
    ----------
    order_manager:
        OMS order manager.
    submit_fn:
        Optional submit callback for :class:`PlaceOrderUseCase`.
    execution_engine:
        Optional execution engine for order placement.
    order_command_fn:
        Optional ADR-012 command function — must route through OMS.
    on_error:
        Optional callback invoked on placement failure (for counter bumps).
    """

    def __init__(
        self,
        order_manager: OrderManager,
        submit_fn: Callable | None = None,
        execution_engine: ExecutionEngine | None = None,
        order_command_fn: Callable[[OmsOrderCommand], OrderResult] | None = None,
        on_error: Callable[[], None] | None = None,
    ) -> None:
        self._order_manager = order_manager
        self._submit_fn = submit_fn
        self._execution_engine = execution_engine
        if order_command_fn is not None and not getattr(
            order_command_fn, "__oms_backed__", False
        ):
            # Soft gate: stamped by runtime.commands.build_order_dispatcher.
            # Hard assert deferred until all composition roots use the factory (F7).
            logger.warning(
                "order_command_fn missing __oms_backed__ stamp; "
                "prefer runtime.commands.build_order_dispatcher(order_manager) "
                "so placement cannot bypass OrderManager.place_order (ADR-012)"
            )
        self._order_command_fn = order_command_fn
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
        """Place *command* through the OMS.

        Parameters
        ----------
        command:
            Order command ready for placement.
        signal:
            Original signal (for audit trail / logging).

        Returns
        -------
        OrderResult:
            Result of order placement.
        """
        try:
            logger.info(
                "Placing order: %s %s %d @ %.2f (correlation=%s)",
                command.side.value,
                command.symbol,
                command.quantity,
                float(command.price),
                command.correlation_id,
            )

            # ADR-012: route through the injected order-command function when
            # wired by the composition root. Must be OMS-backed
            # (build_order_dispatcher → OrderManager.place_order).
            if self._order_command_fn is not None:
                return self._order_command_fn(command)

            if self._execution_engine is not None:
                return self._execution_engine.place_order(command)

            # Prefer PlaceOrderUseCase so bare-OMS never skips the
            # use-case event path.
            return PlaceOrderUseCase(
                self._order_manager,
                submit_fn=self._submit_fn,
            ).execute(command)

        except Exception as exc:
            logger.exception("Order placement failed for %s: %s", command.symbol, exc)
            if self._on_error is not None:
                self._on_error()
            return OrderResult(success=False, error=str(exc))
