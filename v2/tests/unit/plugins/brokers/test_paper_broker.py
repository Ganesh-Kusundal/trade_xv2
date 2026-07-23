"""Tests for paper broker — in-memory simulated execution."""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest

from domain.commands import PlaceOrderCommand
from domain.entities import Account, MarketDepth, Order, Position
from domain.enums import (
    BrokerId,
    OrderSide,
    OrderStatus,
    OrderType,
    TimeInForce,
)
from domain.ports.broker_adapter import BrokerAdapter
from domain.ports.types import BrokerSnapshot
from domain.value_objects import (
    AccountId,
    CorrelationId,
    InstrumentId,
    Money,
    OrderId,
    Price,
    Quantity,
    TimeFrame,
)
from plugins.brokers.paper.adapters.streaming import PaperStreamingAdapter
from plugins.brokers.paper.connection import PaperConnection
from plugins.brokers.paper.gateway import PaperGateway


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def gateway() -> PaperGateway:
    return PaperGateway()


@pytest.fixture()
def buy_command() -> PlaceOrderCommand:
    return PlaceOrderCommand(
        instrument_id=InstrumentId.parse("NSE:RELIANCE"),
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=Quantity(Decimal("10")),
        price=None,
        time_in_force=TimeInForce.DAY,
        correlation_id=CorrelationId(uuid4()),
    )


@pytest.fixture()
def limit_command() -> PlaceOrderCommand:
    return PlaceOrderCommand(
        instrument_id=InstrumentId.parse("NSE:INFY"),
        side=OrderSide.SELL,
        order_type=OrderType.LIMIT,
        quantity=Quantity(Decimal("5")),
        price=Price(Decimal("1500.00")),
        time_in_force=TimeInForce.DAY,
        correlation_id=CorrelationId(uuid4()),
    )


# ---------------------------------------------------------------------------
# Protocol compliance
# ---------------------------------------------------------------------------

class TestProtocolCompliance:
    def test_satisfies_broker_adapter(self, gateway: PaperGateway) -> None:
        assert isinstance(gateway, BrokerAdapter)


# ---------------------------------------------------------------------------
# Order submission
# ---------------------------------------------------------------------------

class TestSubmitOrder:
    def test_returns_order_id(self, gateway: PaperGateway, buy_command: PlaceOrderCommand) -> None:
        oid = gateway.submit_order(buy_command)
        assert isinstance(oid, OrderId)
        assert oid.value  # non-empty

    def test_order_fills_immediately(self, gateway: PaperGateway, buy_command: PlaceOrderCommand) -> None:
        oid = gateway.submit_order(buy_command)
        order = gateway.get_order(oid)
        assert order.status == OrderStatus.FILLED

    def test_stored_order_matches_command(
        self, gateway: PaperGateway, buy_command: PlaceOrderCommand
    ) -> None:
        oid = gateway.submit_order(buy_command)
        order = gateway.get_order(oid)
        assert order.instrument_id == buy_command.instrument_id
        assert order.side == buy_command.side
        assert order.order_type == buy_command.order_type
        assert order.quantity == buy_command.quantity
        assert order.time_in_force == buy_command.time_in_force

    def test_limit_order_fills_at_limit_price(
        self, gateway: PaperGateway, limit_command: PlaceOrderCommand
    ) -> None:
        oid = gateway.submit_order(limit_command)
        order = gateway.get_order(oid)
        assert order.status == OrderStatus.FILLED
        assert order.price == limit_command.price

    def test_unique_order_ids(self, gateway: PaperGateway, buy_command: PlaceOrderCommand) -> None:
        oid1 = gateway.submit_order(buy_command)
        oid2 = gateway.submit_order(buy_command)
        assert oid1 != oid2


# ---------------------------------------------------------------------------
# Order cancellation
# ---------------------------------------------------------------------------

class TestCancelOrder:
    def test_cancel_pending_order(self, gateway: PaperGateway, buy_command: PlaceOrderCommand) -> None:
        # Use auto_fill=False to keep order in SUBMITTED status
        gw = PaperGateway(auto_fill=False)
        oid = gw.submit_order(buy_command)
        order = gw.get_order(oid)
        assert order.status == OrderStatus.SUBMITTED
        gw.cancel_order(oid)
        order = gw.get_order(oid)
        assert order.status == OrderStatus.CANCELLED

    def test_cancel_filled_order_raises(self, gateway: PaperGateway, buy_command: PlaceOrderCommand) -> None:
        # Paper broker fills immediately, so cancel should raise
        oid = gateway.submit_order(buy_command)
        with pytest.raises(ValueError, match="cannot cancel"):
            gateway.cancel_order(oid)

    def test_cancel_submitted_order(self, gateway: PaperGateway) -> None:
        # Use a fresh gateway that doesn't auto-fill
        gw = PaperGateway(auto_fill=False)
        cmd = PlaceOrderCommand(
            instrument_id=InstrumentId.parse("NSE:RELIANCE"),
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=Quantity(Decimal("10")),
            price=None,
            time_in_force=TimeInForce.DAY,
            correlation_id=CorrelationId(uuid4()),
        )
        oid = gw.submit_order(cmd)
        order = gw.get_order(oid)
        assert order.status == OrderStatus.SUBMITTED
        gw.cancel_order(oid)
        order = gw.get_order(oid)
        assert order.status == OrderStatus.CANCELLED


# ---------------------------------------------------------------------------
# Get order / orderbook
# ---------------------------------------------------------------------------

class TestGetOrder:
    def test_get_existing_order(self, gateway: PaperGateway, buy_command: PlaceOrderCommand) -> None:
        oid = gateway.submit_order(buy_command)
        order = gateway.get_order(oid)
        assert order.order_id == oid

    def test_get_nonexistent_order_raises(self, gateway: PaperGateway) -> None:
        with pytest.raises(KeyError):
            gateway.get_order(OrderId("nonexistent"))

    def test_orderbook_contains_all_orders(
        self, gateway: PaperGateway, buy_command: PlaceOrderCommand, limit_command: PlaceOrderCommand
    ) -> None:
        oid1 = gateway.submit_order(buy_command)
        oid2 = gateway.submit_order(limit_command)
        book = gateway.get_orderbook()
        ids = {o.order_id for o in book}
        assert oid1 in ids
        assert oid2 in ids

    def test_orderbook_empty_initially(self, gateway: PaperGateway) -> None:
        assert gateway.get_orderbook() == []


# ---------------------------------------------------------------------------
# Positions
# ---------------------------------------------------------------------------

class TestPositions:
    def test_positions_empty_initially(self, gateway: PaperGateway) -> None:
        assert gateway.get_positions() == []

    def test_buy_order_creates_position(self, gateway: PaperGateway, buy_command: PlaceOrderCommand) -> None:
        gateway.submit_order(buy_command)
        positions = gateway.get_positions()
        assert len(positions) == 1
        pos = positions[0]
        assert pos.instrument_id == InstrumentId.parse("NSE:RELIANCE")
        assert pos.quantity == Quantity(Decimal("10"))

    def test_same_instrument_accumulates_position(
        self, gateway: PaperGateway, buy_command: PlaceOrderCommand
    ) -> None:
        gateway.submit_order(buy_command)
        gateway.submit_order(buy_command)
        positions = gateway.get_positions()
        assert len(positions) == 1
        assert positions[0].quantity == Quantity(Decimal("20"))


# ---------------------------------------------------------------------------
# Funds
# ---------------------------------------------------------------------------

class TestFunds:
    def test_funds_returns_account(self, gateway: PaperGateway) -> None:
        acct = gateway.get_funds()
        assert isinstance(acct, Account)
        assert acct.balance == Money(amount=Decimal("1000000"), currency="INR")

    def test_funds_decrease_after_buy(
        self, gateway: PaperGateway, buy_command: PlaceOrderCommand
    ) -> None:
        initial = gateway.get_funds().balance.amount
        gateway.submit_order(buy_command)
        after = gateway.get_funds().balance.amount
        assert after < initial


# ---------------------------------------------------------------------------
# Mass status
# ---------------------------------------------------------------------------

class TestMassStatus:
    def test_mass_status_returns_snapshot(self, gateway: PaperGateway) -> None:
        snap = gateway.mass_status()
        assert isinstance(snap, BrokerSnapshot)
        assert isinstance(snap.orders, list)
        assert isinstance(snap.positions, list)
        assert isinstance(snap.account, Account)


# ---------------------------------------------------------------------------
# Modify order
# ---------------------------------------------------------------------------

class TestModifyOrder:
    def test_modify_order_updates_price(self, gateway: PaperGateway) -> None:
        gw = PaperGateway(auto_fill=False)
        cmd = PlaceOrderCommand(
            instrument_id=InstrumentId.parse("NSE:RELIANCE"),
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=Quantity(Decimal("10")),
            price=Price(Decimal("2500.00")),
            time_in_force=TimeInForce.DAY,
            correlation_id=CorrelationId(uuid4()),
        )
        oid = gw.submit_order(cmd)
        new_cmd = PlaceOrderCommand(
            instrument_id=InstrumentId.parse("NSE:RELIANCE"),
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=Quantity(Decimal("10")),
            price=Price(Decimal("2450.00")),
            time_in_force=TimeInForce.DAY,
            correlation_id=CorrelationId(uuid4()),
        )
        gw.modify_order(oid, new_cmd)
        order = gw.get_order(oid)
        assert order.price == Price(Decimal("2450.00"))


# ---------------------------------------------------------------------------
# Market data
# ---------------------------------------------------------------------------

class TestMarketData:
    def test_get_ltp_returns_midpoint(self, gateway: PaperGateway) -> None:
        gateway.set_quote(InstrumentId.parse("NSE:RELIANCE"), bid=Decimal("2500.00"), ask=Decimal("2501.00"))
        ltp = gateway.get_ltp(InstrumentId.parse("NSE:RELIANCE"))
        assert ltp.value == Decimal("2500.50")

    def test_get_ltp_no_quote_raises(self, gateway: PaperGateway) -> None:
        with pytest.raises(KeyError):
            gateway.get_ltp(InstrumentId.parse("NSE:MISSING"))

    def test_get_depth_returns_market_depth(self, gateway: PaperGateway) -> None:
        gateway.set_quote(InstrumentId.parse("NSE:RELIANCE"), bid=Decimal("2500.00"), ask=Decimal("2501.00"))
        depth = gateway.get_depth(InstrumentId.parse("NSE:RELIANCE"))
        assert isinstance(depth, MarketDepth)
        assert len(depth.bids) == 1
        assert len(depth.asks) == 1
        assert depth.bids[0].price.value == Decimal("2500.00")
        assert depth.asks[0].price.value == Decimal("2501.00")

    def test_get_depth_no_quote_raises(self, gateway: PaperGateway) -> None:
        with pytest.raises(KeyError):
            gateway.get_depth(InstrumentId.parse("NSE:MISSING"))

    def test_get_history_returns_empty(self, gateway: PaperGateway) -> None:
        gateway.set_quote(InstrumentId.parse("NSE:RELIANCE"), bid=Decimal("2500.00"), ask=Decimal("2501.00"))
        start = datetime.now() - timedelta(days=30)
        end = datetime.now()
        history = gateway.get_history(InstrumentId.parse("NSE:RELIANCE"), TimeFrame(value="1m"), start, end)
        assert history == []


# ---------------------------------------------------------------------------
# Streaming adapter
# ---------------------------------------------------------------------------

@pytest.fixture()
def streaming() -> PaperStreamingAdapter:
    return PaperStreamingAdapter(PaperConnection())


@pytest.fixture()
def iid() -> InstrumentId:
    return InstrumentId.parse("NSE:RELIANCE")


class TestStreamingSubscribe:
    def test_subscribe_adds_to_list(self, streaming: PaperStreamingAdapter, iid: InstrumentId) -> None:
        streaming.subscribe(iid)
        assert iid in streaming.subscriptions

    def test_subscribe_deduplicates(self, streaming: PaperStreamingAdapter, iid: InstrumentId) -> None:
        streaming.subscribe(iid)
        streaming.subscribe(iid)
        assert streaming.subscriptions.count(iid) == 1

    def test_unsubscribe_removes(self, streaming: PaperStreamingAdapter, iid: InstrumentId) -> None:
        streaming.subscribe(iid)
        streaming.unsubscribe(iid)
        assert iid not in streaming.subscriptions


class TestStreamingPush:
    def test_feed_raw_calls_callback(self, streaming: PaperStreamingAdapter, iid: InstrumentId) -> None:
        received: list[tuple] = []
        streaming.stream(iid, lambda iid, q: received.append((iid, q)))
        streaming.feed_raw(iid, {"bid": 2500})
        assert len(received) == 1
        assert received[0][0] == iid
        assert received[0][1] == {"bid": 2500}

    def test_feed_raw_no_callback_is_noop(self, streaming: PaperStreamingAdapter, iid: InstrumentId) -> None:
        streaming.feed_raw(iid, {"bid": 2500})

    def test_unstream_removes_callbacks(self, streaming: PaperStreamingAdapter, iid: InstrumentId) -> None:
        received: list[tuple] = []
        streaming.stream(iid, lambda iid, q: received.append((iid, q)))
        streaming.unstream(iid)
        streaming.feed_raw(iid, {"bid": 2500})
        assert received == []

    def test_multiple_callbacks(self, streaming: PaperStreamingAdapter, iid: InstrumentId) -> None:
        r1: list[tuple] = []
        r2: list[tuple] = []
        streaming.stream(iid, lambda iid, q: r1.append((iid, q)))
        streaming.stream(iid, lambda iid, q: r2.append((iid, q)))
        streaming.feed_raw(iid, {"bid": 2500})
        assert len(r1) == 1
        assert len(r2) == 1


class TestStreamingOrder:
    def test_stream_order_register(self, streaming: PaperStreamingAdapter) -> None:
        received: list[tuple] = []
        streaming.stream_order(lambda oid, status: received.append((oid, status)))
        assert len(streaming._order_callbacks) == 1

    def test_stream_order_multi(self, streaming: PaperStreamingAdapter) -> None:
        streaming.stream_order(lambda oid, s: None)
        streaming.stream_order(lambda oid, s: None)
        assert len(streaming._order_callbacks) == 2


class TestStreamingClose:
    def test_close_clears_everything(self, streaming: PaperStreamingAdapter, iid: InstrumentId) -> None:
        streaming.subscribe(iid)
        streaming.stream(iid, lambda iid, q: None)
        streaming.stream_order(lambda oid, s: None)
        streaming.close()
        assert streaming.subscriptions == []
        assert streaming._quote_callbacks == {}
        assert streaming._order_callbacks == []
