"""Phase 2 safety checks — daily-loss equity delta, durable idempotency, heal, pending TTL."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from application.execution.execution_engine import ExecutionEngine
from application.oms import PositionManager, RiskManager, TradingContext
from application.oms._internal.margin_checker import MarginChecker
from application.oms.order_manager import OmsOrderCommand, OrderManager
from application.oms.risk_manager import RiskConfig
from domain.entities import Order, Trade
from domain.enums import OrderType, ProductType, Side
from domain.events.types import DomainEvent, EventType
from domain.execution_contracts import OrderIntent, SubmissionOutcome
from domain.types import OrderStatus
from infrastructure.event_bus.event_bus import EventBus
from infrastructure.persistence.sqlite_execution_ledger import SqliteExecutionLedger
from infrastructure.persistence.sqlite_order_store import SqliteOrderStore


def _make_trade(trade_id: str, side: Side, price: Decimal, qty: int = 10) -> Trade:
    return Trade(
        trade_id=trade_id,
        order_id="ORD-1",
        symbol="RELIANCE",
        exchange="NSE",
        side=side,
        quantity=qty,
        price=price,
        timestamp=datetime.now(),
    )


def _publish_trade_applied(bus: EventBus, trade: Trade) -> None:
    bus.publish(
        DomainEvent.now(
            EventType.TRADE_APPLIED.value,
            {"trade": trade},
        )
    )


def test_daily_pnl_is_session_equity_delta_not_absolute_mtm(event_bus, processed_trade_repository):
    """F5: overnight underwater book must not trip daily-loss at session open."""
    capital = Decimal("1_000_000")
    pm = PositionManager(event_bus=event_bus)
    # Seed overnight underwater position before context start.
    pm.upsert_position(
        {
            "symbol": "RELIANCE",
            "exchange": "NSE",
            "quantity": 10,
            "avg_price": "2500",
            "ltp": "2000",  # -500 unrealized * 10 = -5000
        }
    )
    rm = RiskManager(pm, RiskConfig(max_daily_loss_pct=Decimal("0.1")), capital_fn=lambda: capital)
    ctx = TradingContext(
        event_bus=event_bus,
        position_manager=pm,
        risk_manager=rm,
        capital_fn=lambda: capital,
        processed_trade_repository=processed_trade_repository,
        replay_events=False,
    )
    # Session-open equity includes overnight MTM; daily delta starts at 0.
    assert ctx.risk_manager.daily_pnl == Decimal("0")
    order = Order(
        order_id="ORD-X",
        symbol="RELIANCE",
        exchange="NSE",
        side=Side.BUY,
        order_type=OrderType.LIMIT,
        quantity=1,
        price=Decimal("2000"),
        product_type=ProductType.INTRADAY,
        correlation_id="c-open",
    )
    assert ctx.risk_manager.check_order(order).allowed is True


def test_daily_pnl_observes_realized_session_loss(event_bus, processed_trade_repository):
    """F5: realized session loss still reaches the risk engine as equity delta."""
    capital = Decimal("1_000_000")
    ctx = TradingContext(
        event_bus=event_bus,
        risk_manager=RiskManager(
            PositionManager(event_bus=event_bus),
            RiskConfig(max_daily_loss_pct=Decimal("5.0")),
            capital_fn=lambda: capital,
        ),
        capital_fn=lambda: capital,
        processed_trade_repository=processed_trade_repository,
        replay_events=False,
    )
    _publish_trade_applied(ctx.event_bus, _make_trade("T1", Side.BUY, Decimal("2500")))
    _publish_trade_applied(ctx.event_bus, _make_trade("T2", Side.SELL, Decimal("2400")))
    assert ctx.risk_manager.daily_pnl == Decimal("-1000")


def test_durable_idempotency_blocks_resubmit_after_restart(tmp_path):
    """F6: correlation recovered from execution ledger must not double-submit."""
    ledger = SqliteExecutionLedger(tmp_path / "ledger.sqlite")
    intent = OrderIntent(
        intent_id="OM-durable1",
        order_id="OM-durable1",
        correlation_id="corr-durable",
        symbol="RELIANCE",
        exchange="NSE",
        side=Side.BUY,
        quantity=10,
        price=Decimal("2500"),
        order_type=OrderType.LIMIT,
        product_type=ProductType.INTRADAY,
        created_at=datetime.now(timezone.utc),
    )
    ledger.record_intent(intent)
    ledger.record_outcome(SubmissionOutcome.accepted(intent.intent_id, "BRK-1"))

    om = OrderManager(execution_ledger=ledger)
    calls: list[str] = []

    def submit_fn(cmd: OmsOrderCommand) -> Order:
        calls.append(cmd.correlation_id)
        return Order(
            order_id="SHOULD-NOT-CREATE",
            symbol=cmd.symbol,
            exchange=cmd.exchange,
            side=cmd.side,
            order_type=cmd.order_type,
            quantity=cmd.quantity,
            price=cmd.price,
            product_type=cmd.product_type,
            correlation_id=cmd.correlation_id,
            status=OrderStatus.OPEN,
        )

    result = om.place_order(
        OmsOrderCommand(
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            quantity=10,
            price=Decimal("2500"),
            order_type=OrderType.LIMIT,
            product_type=ProductType.INTRADAY,
            correlation_id="corr-durable",
        ),
        submit_fn=submit_fn,
    )
    assert result.success is True
    assert result.order is not None
    assert result.order.order_id == "OM-durable1"
    assert calls == []


def test_order_manager_hydrates_correlation_from_store(tmp_path):
    """F6: OrderManager loads durable orders into the correlation hot cache."""
    db = tmp_path / "orders.sqlite"
    store = SqliteOrderStore(db)
    order = Order(
        order_id="OM-hydrated",
        correlation_id="corr-hydrated",
        symbol="RELIANCE",
        exchange="NSE",
        side=Side.BUY,
        order_type=OrderType.MARKET,
        product_type=ProductType.INTRADAY,
        quantity=10,
        status=OrderStatus.OPEN,
    )
    store.upsert(order)
    store.close()

    store2 = SqliteOrderStore(db)
    om = OrderManager(order_store=store2)
    assert om.get_order_by_correlation("corr-hydrated") is not None
    assert om.get_order("OM-hydrated") is not None


class _NullFillSource:
    def submit_fn(self):
        return None


def test_apply_mass_status_heals_missing_local_order(event_bus, processed_trade_repository):
    """F4: apply_mass_status upserts broker orders into the OMS."""
    ctx = TradingContext(
        event_bus=event_bus,
        processed_trade_repository=processed_trade_repository,
        replay_events=False,
    )
    engine = ExecutionEngine(_NullFillSource(), ctx)
    broker_order = Order(
        order_id="BRK-HEAL-1",
        symbol="RELIANCE",
        exchange="NSE",
        side=Side.BUY,
        order_type=OrderType.LIMIT,
        quantity=10,
        price=Decimal("2500"),
        status=OrderStatus.OPEN,
    )
    drift = engine.apply_mass_status(orders=[broker_order], positions=[])
    assert any(d["kind"] == "missing_local_order" for d in drift)
    assert ctx.order_manager.get_order("BRK-HEAL-1") is not None


def test_risk_pending_ttl_expires_stuck_reservation():
    """R2: pending notional expires after TTL so stuck OPEN cannot block forever."""
    checker = MarginChecker(RiskConfig(), pending_ttl_seconds=0.0)
    order = Order(
        order_id="ord-1",
        correlation_id="corr-ttl",
        symbol="RELIANCE",
        exchange="NSE",
        side=Side.BUY,
        order_type=OrderType.LIMIT,
        quantity=10,
        price=Decimal("500"),
        product_type=ProductType.INTRADAY,
    )
    checker.reserve_pending(order, Decimal("5000"))
    assert checker.pending_gross() == Decimal("0")


def test_concentration_includes_in_flight_pending():
    """R4: same-symbol concentration sums pending reservations."""
    capital = Decimal("100000")
    rm = RiskManager(
        PositionManager(),
        RiskConfig(max_position_pct=Decimal("8")),
        capital_fn=lambda: capital,
    )
    first = rm.check_order(
        Order(
            order_id="ord-1",
            correlation_id="corr-a",
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            order_type=OrderType.LIMIT,
            quantity=10,
            price=Decimal("500"),
            product_type=ProductType.INTRADAY,
        )
    )
    assert first.allowed is True
    second = rm.check_order(
        Order(
            order_id="ord-2",
            correlation_id="corr-b",
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            order_type=OrderType.LIMIT,
            quantity=10,
            price=Decimal("500"),
            product_type=ProductType.INTRADAY,
        )
    )
    assert second.allowed is False
    assert "position" in second.reason.lower()


def test_build_order_dispatcher_is_oms_backed():
    """2.5: factory stamps __oms_backed__ and routes through OrderManager."""
    from runtime.commands import build_order_dispatcher

    om = OrderManager()
    fn = build_order_dispatcher(om)
    assert getattr(fn, "__oms_backed__", False) is True
