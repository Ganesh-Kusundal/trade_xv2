"""Unit tests for the Execution aggregate (the previously-missing concept)."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from domain.entities.trade import Trade
from domain.executions.execution import Execution
from domain.instruments.instrument_id import InstrumentId
from domain.tests._fakes import FakeEventBus
from domain.types import Side


def _trade(tid: str, qty: int, price: Decimal) -> Trade:
    return Trade(
        trade_id=tid,
        order_id="ORD1",
        symbol="RELIANCE",
        exchange="NSE",
        side=Side.BUY,
        quantity=qty,
        price=price,
        timestamp=datetime.now(timezone.utc),
    )


def _new_execution(qty: int = 20) -> tuple[Execution, FakeEventBus]:
    bus = FakeEventBus()
    iid = InstrumentId.equity("NSE", "RELIANCE")
    ex = Execution("ORD1", iid, Side.BUY, qty, event_bus=bus)
    return ex, bus


def test_empty_execution():
    ex, _ = _new_execution()
    assert ex.filled_quantity == 0
    assert ex.remaining_quantity == 20
    assert ex.avg_price == Decimal("0")
    assert ex.notional == Decimal("0")
    assert ex.is_complete is False


def test_apply_trade_computes_averages():
    ex, bus = _new_execution(20)
    ex.apply_trade(_trade("t1", 10, Decimal("100")))
    ex.apply_trade(_trade("t2", 10, Decimal("110")))
    assert ex.filled_quantity == 20
    assert ex.remaining_quantity == 0
    assert ex.avg_price == Decimal("105")
    assert ex.notional == Decimal("2100")
    assert ex.is_complete is True
    assert bus.count("TRADE_APPLIED") == 2


def test_partial_fill_remaining():
    ex, _ = _new_execution(50)
    ex.apply_trade(_trade("t1", 30, Decimal("100")))
    assert ex.filled_quantity == 30
    assert ex.remaining_quantity == 20
    assert ex.is_complete is False


def test_trades_immutable_view():
    ex, _ = _new_execution()
    ex.apply_trade(_trade("t1", 5, Decimal("100")))
    trades = ex.trades
    assert len(trades) == 1
    # returned tuple cannot be mutated
    try:
        trades.append(_trade("x", 1, Decimal("1")))  # type: ignore[attr-defined]
        assert False, "trades view should be immutable"
    except AttributeError:
        pass
