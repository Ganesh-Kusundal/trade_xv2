"""Trade recording and event publishing for the OMS OrderManager.

Extracted from :class:`application.oms.order_manager.OrderManager` god class.
Owns the ``_pending_trades_by_order`` buffer, trade idempotency checks
against ``ProcessedTradeRepository``, and ``TRADE_APPLIED`` event publishing.
"""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING

from domain.events.types import DomainEvent, EventType, TradeIdKey

if TYPE_CHECKING:
    from application.oms._internal.order_audit_logger import OrderAuditLogger
    from application.oms._internal.order_position_updater import OrderPositionUpdater
    from domain.entities import Order, Trade
    from domain.ports import EventBusPort, EventMetricsPort, ProcessedTradeRepositoryPort

logger = __import__("logging").getLogger(__name__)


class TradeRecorder:
    """Records trades, enforces trade-level idempotency, and publishes events.

    Maintains a per-order-id buffer for trades that arrive before their
    parent order (race condition in broker event delivery).
    """

    def __init__(
        self,
        processed_trade_repository: ProcessedTradeRepositoryPort | None = None,
        event_bus: EventBusPort | None = None,
        metrics: EventMetricsPort | None = None,
        audit_logger: OrderAuditLogger | None = None,
        position_updater: OrderPositionUpdater | None = None,
        publish_callback: object | None = None,
    ) -> None:
        self._processed_trades = processed_trade_repository
        self._event_bus = event_bus
        self._metrics = metrics
        self._audit_logger = audit_logger
        self._position_updater = position_updater
        self._publish_callback = publish_callback
        self._pending_trades_by_order: dict[str, list[Trade]] = {}
        self._pending_trades_max_per_order: int = 32
        self._trades_processed: int = 0
        self._trades_duplicated: int = 0

    @property
    def trades_processed(self) -> int:
        return self._trades_processed

    @property
    def trades_duplicated(self) -> int:
        return self._trades_duplicated

    def record_trade(
        self,
        lock: threading.RLock,
        orders: dict[str, Order],
        orders_by_correlation: dict[str, Order],
        trade: Trade,
    ) -> bool:
        """Record a trade and update the parent order.

        Idempotent on ``trade.trade_id``: a duplicate trade is logged and
        silently dropped before it can mutate order state.

        After a trade is accepted, the OMS publishes a ``TRADE_APPLIED``
        event that downstream consumers (e.g. :class:`PositionManager`)
        can subscribe to. This is the only way trades should reach the
        position book, so that idempotency is enforced exactly once.

        Returns
        -------
        bool
            True if the trade was accepted and applied.
            False if the trade was a duplicate (already processed) or
            referenced an unknown order (buffered for later).
        """
        if trade.trade_id is None or not str(trade.trade_id).strip():
            raise ValueError("OrderManager.record_trade requires a non-empty trade.trade_id")
        key = TradeIdKey.from_trade(trade)
        with lock:
            if self._processed_trades is not None and self._processed_trades.is_processed(key):
                self._trades_duplicated += 1
                if self._metrics is not None:
                    self._metrics.inc(EventType.TRADE.value, "trade_duplicated")
                logger.info(
                    "OrderManager: trade %s for order %s is a duplicate; skipping",
                    trade.trade_id,
                    trade.order_id,
                )
                return False

            order = orders.get(trade.order_id)
            if order is None:
                buf = self._pending_trades_by_order.setdefault(trade.order_id, [])
                if len(buf) < self._pending_trades_max_per_order:
                    buf.append(trade)
                logger.warning(
                    "OrderManager: trade %s references unknown order %s; "
                    "buffered (%d pending) until order delivery",
                    trade.trade_id,
                    trade.order_id,
                    len(buf),
                )
                return False

            updated = self._position_updater.apply_trade(order, trade)

            orders[order.order_id] = updated
            if order.correlation_id:
                orders_by_correlation[order.correlation_id] = updated

            self._trades_processed += 1
            if self._metrics is not None:
                self._metrics.inc(EventType.TRADE.value, "trade_processed")

            self._audit_logger.log_trade_applied(
                order.order_id,
                trade.trade_id,
                updated.filled_quantity,
                str(updated.avg_price),
                details={
                    "symbol": order.symbol,
                    "status": updated.status.value,
                },
            )

            self._publish_callback(EventType.ORDER_UPDATED.value, updated)
            # R6 (P0): apply to the position book (via TRADE_APPLIED) BEFORE
            # marking the ledger. If we crash after apply but before mark,
            # recovery replays the trade and re-applies it instead of silently
            # skipping an already-marked trade_id (which would lose the fill).
            self._publish_trade_applied(trade)

            if self._processed_trades is not None:
                self._processed_trades.mark_processed(key)
            return True

    def _publish_trade_applied(self, trade: Trade) -> None:
        """Publish a TRADE_APPLIED event after a trade is committed."""
        if self._event_bus is None:
            return
        correlation_id: str | None = getattr(trade, "correlation_id", None)
        self._event_bus.publish(
            DomainEvent.now(
                EventType.TRADE_APPLIED.value,
                {"trade": trade},
                symbol=trade.symbol,
                source="OrderManager",
                correlation_id=correlation_id,
            )
        )

    def flush_pending_trades_locked(
        self,
        lock: threading.RLock,
        orders: dict[str, Order],
        orders_by_correlation: dict[str, Order],
        order_id: str,
    ) -> None:
        """Apply trades buffered before the parent order existed (caller holds lock)."""
        # The caller already holds the lock; no need to acquire it again.
        pending = self._pending_trades_by_order.pop(order_id, None)
        if not pending:
            return
        for trade in pending:
            if self._processed_trades is not None:
                key = TradeIdKey.from_trade(trade)
                if self._processed_trades.is_processed(key):
                    continue
            order = orders.get(trade.order_id)
            if order is None:
                continue
            updated = self._position_updater.apply_trade(order, trade)
            orders[order.order_id] = updated
            if order.correlation_id:
                orders_by_correlation[order.correlation_id] = updated
            self._trades_processed += 1
            self._publish_callback(EventType.ORDER_UPDATED.value, updated)
            # R6 (P0): apply to the position book (via TRADE_APPLIED) BEFORE
            # marking the ledger, so a crash after apply but before mark is
            # recoverable by replay rather than silently skipped.
            self._publish_trade_applied(trade)
            if self._processed_trades is not None:
                self._processed_trades.mark_processed(key)
