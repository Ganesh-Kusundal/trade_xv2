"""Trade recording and event publishing for the OMS OrderManager.

Extracted from :class:`application.oms.order_manager.OrderManager` god class.
Owns the ``_pending_trades_by_order`` buffer, trade idempotency checks
against ``ProcessedTradeRepository``, and ``TRADE_APPLIED`` event publishing.
"""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING

from domain.events.types import DomainEvent, EventType, TradeIdKey
from domain.execution_contracts import LedgerFillRecord
from domain.fill_reducer import FillReducer

if TYPE_CHECKING:
    from domain.ports.execution_ledger import ExecutionLedgerPort
    from application.oms._internal.order_audit_logger import OrderAuditLogger
    from application.oms._internal.order_position_updater import OrderPositionUpdater
    from domain.entities import Order, Trade
    from domain.ports import EventBusPort, EventMetricsPort, ProcessedTradeRepositoryPort

from domain.ports.time_service import ClockPort, get_current_clock

import logging

logger = logging.getLogger(__name__)


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
        execution_ledger: ExecutionLedgerPort | None = None,
        clock: ClockPort | None = None,
    ) -> None:
        self._processed_trades = processed_trade_repository
        self._execution_ledger = execution_ledger
        self._event_bus = event_bus
        self._metrics = metrics
        self._audit_logger = audit_logger
        self._position_updater = position_updater
        self._publish_callback = publish_callback
        self._clock = clock or get_current_clock()
        self._pending_trades_by_order: dict[str, list[Trade]] = {}
        self._pending_trades_max_per_order: int = 32
        self._trades_processed: int = 0
        self._trades_duplicated: int = 0
        self._fill_reducer = FillReducer()

    @property
    def trades_processed(self) -> int:
        return self._trades_processed

    @property
    def trades_duplicated(self) -> int:
        return self._trades_duplicated

    @property
    def execution_ledger(self) -> ExecutionLedgerPort | None:
        """Public accessor for the execution ledger (used by ReconciliationService)."""
        return self._execution_ledger

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

            fill = FillReducer.fill_from_trade(
                trade.trade_id,
                trade.order_id,
                trade.quantity,
                order.filled_quantity,
                trade.price,
            )

            # Mark the trade as processed BEFORE validating/applying it. The
            # repository's mark is the durable idempotency marker; if it raises
            # (simulated crash) the fill is left unmarked and recovery can
            # re-apply it exactly once (R6 / Defect R6). The result also gates
            # the rest of this method: a duplicate (mark returns False) must be
            # skipped without re-applying the fill.
            marked = True
            if self._processed_trades is not None:
                marked = self._processed_trades.mark_processed(key)

            if not marked:
                self._trades_duplicated += 1
                if self._metrics is not None:
                    self._metrics.inc(EventType.TRADE.value, "trade_duplicated")
                logger.info(
                    "OrderManager: trade %s for order %s is a duplicate; skipping",
                    trade.trade_id,
                    trade.order_id,
                )
                return False

            fill_result = self._fill_reducer.apply(
                fill,
                order_quantity=order.quantity,
                prior_cumulative=order.filled_quantity,
            )
            if not fill_result.accepted:
                logger.warning(
                    "OrderManager: trade %s for order %s rejected by fill reducer: %s",
                    trade.trade_id,
                    trade.order_id,
                    fill_result.reason,
                )
                return False

            self._persist_fill_to_ledger(fill, order, trade)

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
            # R6 (P0): apply to the position book (via TRADE_APPLIED) as the
            # last durable step. The trade is already marked processed above, so
            # a crash after apply but before this publish is recovered by replay
            # (mark is set → replay skips the duplicate rather than losing it).
            self._publish_trade_applied(trade)

            # Fast-path guard: record the fill_id only after a successful mark
            # AND apply, so a crashed attempt never poisons the process-wide
            # FillReducer for a later replay.
            self._fill_reducer._seen_fill_ids.add(fill.fill_id)
            return True

    def _persist_fill_to_ledger(self, fill, order: Order, trade: Trade) -> None:
        if self._execution_ledger is None:
            return
        event_time = trade.timestamp
        if event_time is not None and event_time.tzinfo is None:
            from datetime import timezone

            event_time = event_time.replace(tzinfo=timezone.utc)
        if event_time is None:
            event_time = self._clock.now()
        record = LedgerFillRecord(
            fill_id=str(trade.trade_id),
            order_id=trade.order_id,
            symbol=trade.symbol,
            exchange=trade.exchange,
            side=trade.side,
            quantity=trade.quantity,
            cumulative_quantity=fill.cumulative_quantity,
            order_quantity=order.quantity,
            price=trade.price,
            event_time=event_time,
        )
        self._execution_ledger.record_fill(record)

    def _publish_trade_applied(self, trade: Trade) -> None:
        """Publish a TRADE_APPLIED event after a trade is committed."""
        if self._event_bus is None:
            return
        correlation_id: str | None = getattr(trade, "correlation_id", None)
        self._event_bus.publish(
            DomainEvent.now(
                EventType.TRADE_APPLIED.value,
                {"trade": trade},
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
            fill = FillReducer.fill_from_trade(
                trade.trade_id,
                trade.order_id,
                trade.quantity,
                order.filled_quantity,
                trade.price,
            )
            # Mark before apply (see record_trade): the repository mark is the
            # durable idempotency marker; a crash leaves the reducer clean for
            # replay. Skip if the mark rejects (already processed).
            marked = True
            if self._processed_trades is not None:
                marked = self._processed_trades.mark_processed(key)
            if not marked:
                continue
            fill_result = self._fill_reducer.apply(
                fill,
                order_quantity=order.quantity,
                prior_cumulative=order.filled_quantity,
            )
            if not fill_result.accepted:
                logger.warning(
                    "OrderManager: buffered trade %s for order %s rejected by fill reducer: %s",
                    trade.trade_id,
                    trade.order_id,
                    fill_result.reason,
                )
                continue
            self._persist_fill_to_ledger(fill, order, trade)
            updated = self._position_updater.apply_trade(order, trade)
            orders[order.order_id] = updated
            if order.correlation_id:
                orders_by_correlation[order.correlation_id] = updated
            self._trades_processed += 1
            self._publish_callback(EventType.ORDER_UPDATED.value, updated)
            # R6 (P0): apply to the position book (via TRADE_APPLIED) as the
            # last durable step; the mark above already gates duplicates.
            self._publish_trade_applied(trade)
            self._fill_reducer._seen_fill_ids.add(fill.fill_id)
