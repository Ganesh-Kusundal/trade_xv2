"""Regression test for Defect R6 (P0): trade ledger must be marked AFTER apply.

Previously ``TradeRecorder.record_trade`` called ``mark_processed(...)`` and
*then* ``apply_trade(...)`` / published ``TRADE_APPLIED``. A crash between the
two steps advanced the durable ledger but never applied the fill; on restart
recovery saw the trade as already-processed and SKIPPED re-applying it, causing
a silent missing position / lost fill.

The fix (plan C0.5) reorders the operations so the trade is applied to the
order/position state FIRST and the ledger is marked LAST. A crash after apply
but before mark now means recovery replays the trade and re-applies it.

This test proves two things:

1. ``apply`` is invoked *before* ``mark_processed`` (call-order contract).
2. A simulated crash between apply and mark (``mark_processed`` raises) does
   NOT lose the fill: after a restart (fresh order book, same ledger) the
   trade is re-applied exactly once, not skipped.
"""

from __future__ import annotations

import threading
from unittest.mock import MagicMock

import pytest

from application.oms.order_manager import OrderManager
from domain import Order, OrderStatus, OrderType, Side, Trade
from domain.events.types import EventType
from infrastructure.event_bus import ProcessedTradeRepository


def _make_order(order_id: str = "O1", quantity: int = 10) -> Order:
    return Order(
        order_id=order_id,
        symbol="RELIANCE",
        exchange="NSE",
        side=Side.BUY,
        order_type=OrderType.MARKET,
        quantity=quantity,
        price="2500",
        status=OrderStatus.OPEN,
    )


def _make_trade(trade_id: str = "T1", order_id: str = "O1", quantity: int = 5) -> Trade:
    return Trade(
        trade_id=trade_id,
        order_id=order_id,
        symbol="RELIANCE",
        exchange="NSE",
        side=Side.BUY,
        quantity=quantity,
        price="2500",
    )


@pytest.fixture
def repo() -> ProcessedTradeRepository:
    # In-memory ledger (no persistence_path) — safe for tests.
    return ProcessedTradeRepository()


@pytest.fixture
def order_manager(repo: ProcessedTradeRepository) -> OrderManager:
    return OrderManager(processed_trade_repository=repo)


def test_apply_happens_before_mark(
    order_manager: OrderManager,
    repo: ProcessedTradeRepository,
) -> None:
    """The recorder must apply the trade before marking the ledger.

    We use a fake recorder that records the order of ``apply_trade`` vs
    ``mark_processed`` calls on the repository.
    """
    order_manager.upsert_order(_make_order())

    calls: list[str] = []

    real_apply = order_manager._trade_recorder._position_updater.apply_trade
    real_mark = repo.mark_processed

    def spy_apply(order: Order, trade: Trade) -> Order:
        calls.append("apply")
        return real_apply(order, trade)

    def spy_mark(key) -> None:
        calls.append("mark")
        real_mark(key)

    order_manager._trade_recorder._position_updater.apply_trade = spy_apply  # type: ignore[assignment]
    repo.mark_processed = spy_mark  # type: ignore[method-assign]

    assert order_manager.record_trade(_make_trade()) is True
    assert calls == ["apply", "mark"], f"expected apply before mark, got {calls}"


def test_crash_between_apply_and_mark_reapplies_on_replay(
    order_manager: OrderManager,
    repo: ProcessedTradeRepository,
) -> None:
    """Simulate a crash (mark_processed raises) after apply but before mark.

    After the crash we simulate a process restart: the in-memory order book is
    rebuilt from scratch (fresh OPEN order) while the durable ledger is the
    same instance (it was never marked). Replaying the trade must re-apply the
    fill exactly once — NOT skip it as an already-processed trade.
    """
    order_manager.upsert_order(_make_order())

    # 1) First attempt: apply succeeds, but mark_processed crashes.
    def boom(key) -> None:
        raise RuntimeError("simulated crash before ledger mark")

    repo.mark_processed = boom  # type: ignore[method-assign]

    with pytest.raises(RuntimeError):
        order_manager.record_trade(_make_trade())

    # The order book was mutated in-memory, but a real crash would discard it.
    # Simulate restart: drop the in-memory book and rebuild from broker state.
    with order_manager._lock:
        order_manager._orders.clear()
        order_manager._orders_by_correlation.clear()
    order_manager.upsert_order(_make_order())  # broker re-delivers the OPEN order

    # 2) Recovery replay: ledger was never marked, so is_processed() is False
    #    and the trade must be re-applied (not skipped).
    repo.mark_processed = MagicMock()  # restore a working ledger mark

    assert order_manager.record_trade(_make_trade()) is True

    recovered = order_manager.get_order("O1")
    assert recovered is not None
    # Re-applied exactly once on a fresh book → filled == trade quantity.
    assert recovered.filled_quantity == 5, (
        f"fill was lost or double-counted: {recovered.filled_quantity}"
    )
    assert repo.mark_processed.called  # ledger finally marked on recovery


def test_no_double_apply_when_ledger_already_marked(
    order_manager: OrderManager,
    repo: ProcessedTradeRepository,
) -> None:
    """Sanity: a trade whose ledger IS marked must be skipped (no double fill)."""
    order_manager.upsert_order(_make_order())
    assert order_manager.record_trade(_make_trade()) is True

    # Second delivery: ledger already marked → must be skipped, not re-applied.
    assert order_manager.record_trade(_make_trade()) is False
    order = order_manager.get_order("O1")
    assert order is not None
    assert order.filled_quantity == 5  # NOT 10


def test_trade_applied_event_published_before_mark(
    order_manager: OrderManager,
    repo: ProcessedTradeRepository,
) -> None:
    """TRADE_APPLIED (which drives the position book) must fire before mark."""
    seen: list[str] = []
    # _publish_trade_applied() uses the recorder's own event bus, not the
    # OrderManager's, so patch the recorder's bus.
    order_manager._trade_recorder._event_bus = _RecordingBus(seen)  # type: ignore[assignment]
    order_manager.upsert_order(_make_order())

    real_mark = repo.mark_processed

    def spy_mark(key) -> None:
        seen.append("mark")
        real_mark(key)

    repo.mark_processed = spy_mark  # type: ignore[method-assign]

    assert order_manager.record_trade(_make_trade()) is True
    assert seen == [EventType.TRADE_APPLIED.value, "mark"], (
        f"TRADE_APPLIED must precede mark; got {seen}"
    )


class _RecordingBus:
    """Minimal event bus that records published event types in order."""

    def __init__(self, sink: list[str]) -> None:
        self._sink = sink
        self._lock = threading.RLock()

    def publish(self, event) -> None:
        self._sink.append(event.event_type)
