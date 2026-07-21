"""Graceful shutdown sequence for the OMS.

Coordinates kill-switch activation, order cancellation, event-log flushing,
and SYSTEM_SHUTDOWN event publication.  Extracted from TradingContext so the
shutdown logic can be tested and reasoned about in isolation.

Dependency direction
--------------------
``context.py`` → ``shutdown_coordinator.py`` (one-way, no cycle).
The coordinator receives concrete ports/ managers through its constructor
and never imports from ``context.py``.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from application.oms._internal.risk_manager import RiskManager
    from application.oms.order_manager import OrderManager
    from domain.ports import EventBusPort, EventLogPort

logger = logging.getLogger(__name__)


class ShutdownCoordinator:
    """Execute the graceful shutdown sequence for the trading context.

    Steps:
        1. Activate kill switch to halt new order placement.
        2. Cancel all open orders (optionally via a broker gateway).
        3. Flush and close the event log.
        4. Publish a SYSTEM_SHUTDOWN event.

    Parameters
    ----------
    risk_manager:
        Used to activate the kill switch (step 1).
    order_manager:
        Source of open orders and target for local cancellation (step 2).
    event_bus:
        Used to publish the SYSTEM_SHUTDOWN event (step 4).
    event_log:
        Flushed and closed in step 3.  May be ``None``.
    service_name:
        Identifier included in the SYSTEM_SHUTDOWN event payload.
    """

    def __init__(
        self,
        risk_manager: RiskManager,
        order_manager: OrderManager,
        event_bus: EventBusPort,
        event_log: EventLogPort | None,
        service_name: str = "oms.trading_context",
    ) -> None:
        self._risk_manager = risk_manager
        self._order_manager = order_manager
        self._event_bus = event_bus
        self._event_log = event_log
        self.name = service_name

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def execute(
        self,
        cancel_orders: bool = True,
        gateway: Any | None = None,
    ) -> dict[str, Any]:
        """Run the full shutdown sequence and return a result dict.

        Parameters
        ----------
        cancel_orders:
            When *True* (default), open orders are cancelled before
            flushing the event log.
        gateway:
            Optional broker gateway for remote cancellation.  When
            *None*, orders are cancelled locally only.
        """
        from domain.events.types import DomainEvent, EventType

        result: dict[str, Any] = {
            "orders_cancelled": 0,
            "orders_failed": 0,
            "event_log_flushed": False,
            "connections_closed": 0,
        }

        # Step 1: Halt new order placement
        try:
            self._risk_manager.set_kill_switch(True)
            logger.info("TradingContext: kill switch activated")
        except Exception as exc:
            logger.warning("TradingContext: kill_switch activation failed: %s", exc)

        # Step 2: Cancel all open orders
        if cancel_orders:
            cancelled, failed, _failed_ids = self.cancel_all(gateway=gateway)
            result["orders_cancelled"] = cancelled
            result["orders_failed"] = failed
            logger.info(
                "TradingContext: order cancellation complete — cancelled=%d, failed=%d",
                result["orders_cancelled"],
                result["orders_failed"],
            )

        # Step 3: Flush event log to disk
        if self._event_log is not None:
            try:
                if hasattr(self._event_log, "flush"):
                    self._event_log.flush()
                self._event_log.close()
                result["event_log_flushed"] = True
                logger.info("TradingContext: event log flushed and closed")
            except Exception as exc:
                logger.warning("TradingContext: event_log flush/close failed: %s", exc)

        # Step 4: Emit SYSTEM_SHUTDOWN event
        try:
            self._event_bus.publish(
                DomainEvent.now(
                    EventType.SYSTEM_SHUTDOWN.value,
                    payload={
                        "service_name": self.name,
                        "detail": "shutdown_complete",
                        "orders_cancelled": result["orders_cancelled"],
                        "orders_failed": result["orders_failed"],
                    },
                    source="TradingContext",
                )
            )
        except Exception as exc:
            logger.warning("TradingContext: SYSTEM_SHUTDOWN event publish failed: %s", exc)

        return result

    def cancel_all(
        self,
        gateway: Any | None = None,
    ) -> tuple[int, int, tuple[str, ...]]:
        """Cancel every OPEN order in the OMS, optionally via a broker gateway.

        For each OPEN order:
            1. If *gateway* is provided, call ``gateway.cancel_order()``.
            2. Update local order status to CANCELLED.
            3. Collect successes / failures.

        Returns
        -------
        Tuple of ``(cancelled_count, failed_count, failed_order_ids)``.
        """
        from domain.enums import OrderStatus

        cancelled = 0
        failed = 0
        failed_ids: list[str] = []

        open_orders = [
            order for order in self._order_manager.get_orders() if order.status == OrderStatus.OPEN
        ]

        if not open_orders:
            logger.debug("TradingContext: no open orders to cancel")
            return 0, 0, ()

        logger.info("TradingContext: cancelling %d open orders", len(open_orders))

        for order in open_orders:
            try:
                if gateway is not None:
                    try:
                        cancel_response = gateway.cancel_order(order.order_id)
                        if not getattr(cancel_response, "success", False):
                            msg = getattr(cancel_response, "message", "unknown")
                            logger.error(
                                "TradingContext: broker cancel failed for %s: %s",
                                order.order_id,
                                msg,
                            )
                            failed += 1
                            failed_ids.append(order.order_id)
                            continue
                    except Exception as exc:
                        logger.error(
                            "TradingContext: gateway.cancel_order(%s) raised: %s: %s",
                            order.order_id,
                            type(exc).__name__,
                            exc,
                        )
                        failed += 1
                        failed_ids.append(order.order_id)
                        continue

                cancel_result = self._order_manager.cancel_order(order.order_id)
                if cancel_result.success:
                    cancelled += 1
                else:
                    logger.warning(
                        "TradingContext: local cancel failed for %s: %s",
                        order.order_id,
                        cancel_result.error,
                    )
                    failed += 1
                    failed_ids.append(order.order_id)

            except Exception as exc:
                logger.error(
                    "TradingContext: unexpected error cancelling %s: %s: %s",
                    order.order_id,
                    type(exc).__name__,
                    exc,
                )
                failed += 1
                failed_ids.append(order.order_id)

        return cancelled, failed, tuple(failed_ids)
