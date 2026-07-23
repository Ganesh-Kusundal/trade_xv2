"""Domain messages are immutable and form a proper hierarchy."""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from domain.enums import (
    BrokerId,
    ComponentState,
    DriftSeverity,
    Environment,
    OrderSide,
    OrderType,
    RiskLevel,
    SignalDirection,
    TimeInForce,
)
from domain.events import (
    AccountUpdated,
    AutoFlattenOrder,
    BacktestCompleted,
    Bar,
    BrokerDisconnected,
    BrokerReconnected,
    ComponentHealth,
    FeatureComputed,
    MarketDataMessage,
    Message,
    OrderCancelled,
    OrderCommand,
    OrderFilled,
    OrderMessage,
    OrderModified,
    OrderPlaced,
    OrderRejected,
    OrderBook,
    PortfolioMessage,
    PnLUpdated,
    PositionUpdated,
    Quote,
    RankMessage,
    RankingUpdated,
    ReconciliationCompleted,
    ReconciliationDrift,
    ReplayCompleted,
    ReplayStarted,
    RiskAlert,
    RiskCheckResult,
    RiskMessage,
    RiskRejected,
    ScanCompleted,
    SignalGenerated,
    Startup,
    Shutdown,
    SystemMessage,
    Tick,
    Trade,
)
from domain.value_objects import (
    AccountId,
    ComponentId,
    InstrumentId,
    OrderId,
    Price,
    Quantity,
    StrategyId,
    TimeFrame,
)

def _ts() -> datetime:
    return datetime(2024, 6, 1, 12, 0, tzinfo=UTC)


def _cid():
    return uuid4()


def _inst(s: str = "NSE:RELIANCE") -> InstrumentId:
    return InstrumentId.parse(s)


def _price(v: str = "100.50") -> Price:
    return Price(value=Decimal(v))


def _qty(v: str = "10") -> Quantity:
    return Quantity(value=Decimal(v))


def _order_id(s: str = "O-001") -> OrderId:
    return OrderId(value=s)


def _account(s: str = "ACC-001") -> AccountId:
    return AccountId(value=s)


def _strategy(s: str = "STRAT-001") -> StrategyId:
    return StrategyId(value=s)


def _component(s: str = "oms") -> ComponentId:
    return ComponentId(value=s)


# ---------------------------------------------------------------------------
# Base Message
# ---------------------------------------------------------------------------

class TestMessageBase:
    def test_is_frozen(self) -> None:
        msg = Message(timestamp=_ts())
        with pytest.raises(Exception):
            msg.timestamp = 0  # type: ignore[misc]

    def test_default_fields(self) -> None:
        msg = Message(timestamp=_ts())
        assert msg.correlation_id is None
        assert msg.source is None

    def test_with_optional_fields(self) -> None:
        cid = _cid()
        src = _component()
        msg = Message(timestamp=_ts(), correlation_id=cid, source=src)
        assert msg.correlation_id == cid
        assert msg.source == src


# ---------------------------------------------------------------------------
# Market Data Messages
# ---------------------------------------------------------------------------

class TestQuote:
    def test_inherits_message(self) -> None:
        q = Quote(timestamp=_ts(), instrument_id=_inst(), bid_price=_price(), ask_price=_price("101"), bid_size=_qty(), ask_size=_qty())
        assert isinstance(q, Message)
        assert isinstance(q, MarketDataMessage)

    def test_frozen(self) -> None:
        q = Quote(timestamp=_ts(), instrument_id=_inst(), bid_price=_price(), ask_price=_price("101"), bid_size=_qty(), ask_size=_qty())
        with pytest.raises(Exception):
            q.bid_price = _price("99")  # type: ignore[misc]


class TestTrade:
    def test_inherits_message(self) -> None:
        t = Trade(timestamp=_ts(), instrument_id=_inst(), price=_price(), size=_qty())
        assert isinstance(t, MarketDataMessage)

    def test_frozen(self) -> None:
        t = Trade(timestamp=_ts(), instrument_id=_inst(), price=_price(), size=_qty())
        with pytest.raises(Exception):
            t.price = _price("99")  # type: ignore[misc]


class TestBar:
    def test_inherits_message(self) -> None:
        b = Bar(
            timestamp=_ts(), instrument_id=_inst(),
            open=_price(), high=_price("110"), low=_price("90"), close=_price("105"),
            volume=_qty("1000"), timeframe=TimeFrame(value="1m"),
        )
        assert isinstance(b, MarketDataMessage)

    def test_frozen(self) -> None:
        b = Bar(
            timestamp=_ts(), instrument_id=_inst(),
            open=_price(), high=_price("110"), low=_price("90"), close=_price("105"),
            volume=_qty("1000"), timeframe=TimeFrame(value="1m"),
        )
        with pytest.raises(Exception):
            b.close = _price("0")  # type: ignore[misc]


class TestOrderBook:
    def test_inherits_message(self) -> None:
        ob = OrderBook(
            timestamp=_ts(), instrument_id=_inst(),
            bids=((_price("99"), _qty("5")),),
            asks=((_price("101"), _qty("3")),),
        )
        assert isinstance(ob, MarketDataMessage)

    def test_frozen(self) -> None:
        ob = OrderBook(
            timestamp=_ts(), instrument_id=_inst(),
            bids=((_price("99"), _qty("5")),),
            asks=((_price("101"), _qty("3")),),
        )
        with pytest.raises(Exception):
            ob.bids = ()  # type: ignore[misc]


class TestTick:
    def test_inherits_message(self) -> None:
        tk = Tick(timestamp=_ts(), instrument_id=_inst(), price=_price(), size=_qty(), side=OrderSide.BUY)
        assert isinstance(tk, MarketDataMessage)

    def test_frozen(self) -> None:
        tk = Tick(timestamp=_ts(), instrument_id=_inst(), price=_price(), size=_qty(), side=OrderSide.BUY)
        with pytest.raises(Exception):
            tk.side = OrderSide.SELL  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Order Messages
# ---------------------------------------------------------------------------

class TestOrderCommand:
    def test_inherits_message(self) -> None:
        cmd = OrderCommand(
            timestamp=_ts(), instrument_id=_inst(), side=OrderSide.BUY,
            order_type=OrderType.LIMIT, quantity=_qty(), price=_price(),
            time_in_force=TimeInForce.DAY,
        )
        assert isinstance(cmd, OrderMessage)

    def test_frozen(self) -> None:
        cmd = OrderCommand(
            timestamp=_ts(), instrument_id=_inst(), side=OrderSide.BUY,
            order_type=OrderType.LIMIT, quantity=_qty(), price=_price(),
            time_in_force=TimeInForce.DAY,
        )
        with pytest.raises(Exception):
            cmd.quantity = _qty("99")  # type: ignore[misc]


class TestOrderPlaced:
    def test_inherits_message(self) -> None:
        op = OrderPlaced(timestamp=_ts(), order_id=_order_id(), instrument_id=_inst(), side=OrderSide.BUY, quantity=_qty())
        assert isinstance(op, OrderMessage)

    def test_frozen(self) -> None:
        op = OrderPlaced(timestamp=_ts(), order_id=_order_id(), instrument_id=_inst(), side=OrderSide.BUY, quantity=_qty())
        with pytest.raises(Exception):
            op.order_id = _order_id("X")  # type: ignore[misc]


class TestOrderFilled:
    def test_inherits_message(self) -> None:
        of = OrderFilled(
            timestamp=_ts(), order_id=_order_id(), instrument_id=_inst(),
            side=OrderSide.BUY, filled_qty=_qty(), avg_price=_price(),
        )
        assert isinstance(of, OrderMessage)

    def test_frozen(self) -> None:
        of = OrderFilled(
            timestamp=_ts(), order_id=_order_id(), instrument_id=_inst(),
            side=OrderSide.BUY, filled_qty=_qty(), avg_price=_price(),
        )
        with pytest.raises(Exception):
            of.avg_price = _price("0")  # type: ignore[misc]


class TestOrderCancelled:
    def test_inherits_message(self) -> None:
        oc = OrderCancelled(timestamp=_ts(), order_id=_order_id(), reason="user")
        assert isinstance(oc, OrderMessage)

    def test_frozen(self) -> None:
        oc = OrderCancelled(timestamp=_ts(), order_id=_order_id(), reason="user")
        with pytest.raises(Exception):
            oc.reason = ""  # type: ignore[misc]


class TestOrderRejected:
    def test_inherits_message(self) -> None:
        orr = OrderRejected(timestamp=_ts(), order_id=_order_id(), reason="risk", venue_code="RISK")
        assert isinstance(orr, OrderMessage)

    def test_frozen(self) -> None:
        orr = OrderRejected(timestamp=_ts(), order_id=_order_id(), reason="risk", venue_code="RISK")
        with pytest.raises(Exception):
            orr.venue_code = ""  # type: ignore[misc]


class TestOrderModified:
    def test_inherits_message(self) -> None:
        om = OrderModified(timestamp=_ts(), order_id=_order_id(), new_quantity=_qty("20"), new_price=_price("110"))
        assert isinstance(om, OrderMessage)

    def test_frozen(self) -> None:
        om = OrderModified(timestamp=_ts(), order_id=_order_id(), new_quantity=_qty("20"), new_price=_price("110"))
        with pytest.raises(Exception):
            om.new_quantity = _qty("0")  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Portfolio Messages
# ---------------------------------------------------------------------------

class TestPositionUpdated:
    def test_inherits_message(self) -> None:
        pu = PositionUpdated(
            timestamp=_ts(), account_id=_account(), instrument_id=_inst(),
            quantity=_qty(), avg_price=_price(), realized_pnl=_price("0"),
            unrealized_pnl=_price("100"),
        )
        assert isinstance(pu, PortfolioMessage)

    def test_frozen(self) -> None:
        pu = PositionUpdated(
            timestamp=_ts(), account_id=_account(), instrument_id=_inst(),
            quantity=_qty(), avg_price=_price(), realized_pnl=_price("0"),
            unrealized_pnl=_price("100"),
        )
        with pytest.raises(Exception):
            pu.quantity = _qty("0")  # type: ignore[misc]


class TestAccountUpdated:
    def test_inherits_message(self) -> None:
        au = AccountUpdated(timestamp=_ts(), account_id=_account(), balance=_price("100000"), margin=_price("50000"), equity=_price("150000"))
        assert isinstance(au, PortfolioMessage)

    def test_frozen(self) -> None:
        au = AccountUpdated(timestamp=_ts(), account_id=_account(), balance=_price("100000"), margin=_price("50000"), equity=_price("150000"))
        with pytest.raises(Exception):
            au.balance = _price("0")  # type: ignore[misc]


class TestPnLUpdated:
    def test_inherits_message(self) -> None:
        pnl = PnLUpdated(timestamp=_ts(), account_id=_account(), realized=_price("500"), unrealized=_price("200"), total=_price("700"))
        assert isinstance(pnl, PortfolioMessage)

    def test_frozen(self) -> None:
        pnl = PnLUpdated(timestamp=_ts(), account_id=_account(), realized=_price("500"), unrealized=_price("200"), total=_price("700"))
        with pytest.raises(Exception):
            pnl.total = _price("0")  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Risk Messages
# ---------------------------------------------------------------------------

class TestRiskCheckResult:
    def test_inherits_message(self) -> None:
        rcr = RiskCheckResult(timestamp=_ts(), approved=True, reason="", max_quantity=_qty("100"), max_notional=_price("1000000"))
        assert isinstance(rcr, RiskMessage)

    def test_frozen(self) -> None:
        rcr = RiskCheckResult(timestamp=_ts(), approved=True, reason="", max_quantity=_qty("100"), max_notional=_price("1000000"))
        with pytest.raises(Exception):
            rcr.approved = False  # type: ignore[misc]


class TestRiskRejected:
    def test_inherits_message(self) -> None:
        rr = RiskRejected(timestamp=_ts(), order_id=_order_id(), reason="limit_exceeded", correlation_id=_cid())
        assert isinstance(rr, RiskMessage)

    def test_frozen(self) -> None:
        rr = RiskRejected(timestamp=_ts(), order_id=_order_id(), reason="limit_exceeded", correlation_id=_cid())
        with pytest.raises(Exception):
            rr.reason = ""  # type: ignore[misc]


class TestRiskAlert:
    def test_inherits_message(self) -> None:
        ra = RiskAlert(timestamp=_ts(), level=RiskLevel.WARNING, reason="high_exposure", instrument_id=_inst())
        assert isinstance(ra, RiskMessage)

    def test_frozen(self) -> None:
        ra = RiskAlert(timestamp=_ts(), level=RiskLevel.WARNING, reason="high_exposure", instrument_id=_inst())
        with pytest.raises(Exception):
            ra.level = RiskLevel.INFO  # type: ignore[misc]


class TestAutoFlattenOrder:
    def test_inherits_message(self) -> None:
        af = AutoFlattenOrder(timestamp=_ts(), instrument_id=_inst(), reason="risk_breach")
        assert isinstance(af, RiskMessage)

    def test_frozen(self) -> None:
        af = AutoFlattenOrder(timestamp=_ts(), instrument_id=_inst(), reason="risk_breach")
        with pytest.raises(Exception):
            af.reason = ""  # type: ignore[misc]


# ---------------------------------------------------------------------------
# System Messages
# ---------------------------------------------------------------------------

class TestStartup:
    def test_inherits_message(self) -> None:
        s = Startup(timestamp=_ts(), environment=Environment.LIVE, broker_id=BrokerId.DHAN, config_hash="abc123")
        assert isinstance(s, SystemMessage)

    def test_frozen(self) -> None:
        s = Startup(timestamp=_ts(), environment=Environment.LIVE, broker_id=BrokerId.DHAN, config_hash="abc123")
        with pytest.raises(Exception):
            s.environment = Environment.BACKTEST  # type: ignore[misc]


class TestShutdown:
    def test_inherits_message(self) -> None:
        s = Shutdown(timestamp=_ts(), reason="user_initiated")
        assert isinstance(s, SystemMessage)

    def test_frozen(self) -> None:
        s = Shutdown(timestamp=_ts(), reason="user_initiated")
        with pytest.raises(Exception):
            s.reason = ""  # type: ignore[misc]


class TestComponentHealth:
    def test_inherits_message(self) -> None:
        ch = ComponentHealth(
            timestamp=_ts(), component_id=_component(), state=ComponentState.RUNNING,
            metrics={"latency_ms": 1.5},
        )
        assert isinstance(ch, SystemMessage)

    def test_frozen(self) -> None:
        ch = ComponentHealth(
            timestamp=_ts(), component_id=_component(), state=ComponentState.RUNNING,
            metrics={"latency_ms": 1.5},
        )
        with pytest.raises(Exception):
            ch.state = ComponentState.ERROR  # type: ignore[misc]


class TestReconciliationDrift:
    def test_inherits_message(self) -> None:
        rd = ReconciliationDrift(timestamp=_ts(), drift_items=["qty_mismatch"], severity=DriftSeverity.HIGH)
        assert isinstance(rd, SystemMessage)

    def test_frozen(self) -> None:
        rd = ReconciliationDrift(timestamp=_ts(), drift_items=["qty_mismatch"], severity=DriftSeverity.HIGH)
        with pytest.raises(Exception):
            rd.severity = DriftSeverity.LOW  # type: ignore[misc]


class TestReconciliationCompleted:
    def test_inherits_message(self) -> None:
        rc = ReconciliationCompleted(timestamp=_ts(), items_healed=5, duration_ms=120)
        assert isinstance(rc, SystemMessage)

    def test_frozen(self) -> None:
        rc = ReconciliationCompleted(timestamp=_ts(), items_healed=5, duration_ms=120)
        with pytest.raises(Exception):
            rc.items_healed = 0  # type: ignore[misc]


class TestBrokerDisconnected:
    def test_inherits_message(self) -> None:
        bd = BrokerDisconnected(timestamp=_ts(), broker_id=BrokerId.DHAN, reason="timeout")
        assert isinstance(bd, SystemMessage)

    def test_frozen(self) -> None:
        bd = BrokerDisconnected(timestamp=_ts(), broker_id=BrokerId.DHAN, reason="timeout")
        with pytest.raises(Exception):
            bd.reason = ""  # type: ignore[misc]


class TestBrokerReconnected:
    def test_inherits_message(self) -> None:
        br = BrokerReconnected(timestamp=_ts(), broker_id=BrokerId.DHAN)
        assert isinstance(br, SystemMessage)

    def test_frozen(self) -> None:
        br = BrokerReconnected(timestamp=_ts(), broker_id=BrokerId.DHAN)
        with pytest.raises(Exception):
            br.broker_id = BrokerId.PAPER  # type: ignore[misc]


class TestReplayStarted:
    def test_inherits_message(self) -> None:
        rs = ReplayStarted(timestamp=_ts(), session_id="sess-1", start_ts=datetime(2024, 6, 1, 12, 0, 1, tzinfo=UTC), end_ts=datetime(2024, 6, 1, 12, 0, 2, tzinfo=UTC))
        assert isinstance(rs, SystemMessage)

    def test_frozen(self) -> None:
        rs = ReplayStarted(timestamp=_ts(), session_id="sess-1", start_ts=datetime(2024, 6, 1, 12, 0, 1, tzinfo=UTC), end_ts=datetime(2024, 6, 1, 12, 0, 2, tzinfo=UTC))
        with pytest.raises(Exception):
            rs.session_id = ""  # type: ignore[misc]


class TestReplayCompleted:
    def test_inherits_message(self) -> None:
        rc = ReplayCompleted(timestamp=_ts(), session_id="sess-1", events_replayed=500, duration_ms=300)
        assert isinstance(rc, SystemMessage)

    def test_frozen(self) -> None:
        rc = ReplayCompleted(timestamp=_ts(), session_id="sess-1", events_replayed=500, duration_ms=300)
        with pytest.raises(Exception):
            rc.events_replayed = 0  # type: ignore[misc]


class TestFeatureComputed:
    def test_inherits_message(self) -> None:
        fc = FeatureComputed(
            timestamp=_ts(), instrument_id=_inst(), feature_name="rsi_14",
            value=_price("65.3"), feature_timestamp=datetime(2024, 6, 1, 12, 0, 1, tzinfo=UTC),
        )
        assert isinstance(fc, SystemMessage)

    def test_frozen(self) -> None:
        fc = FeatureComputed(
            timestamp=_ts(), instrument_id=_inst(), feature_name="rsi_14",
            value=_price("65.3"), feature_timestamp=datetime(2024, 6, 1, 12, 0, 1, tzinfo=UTC),
        )
        with pytest.raises(Exception):
            fc.feature_name = ""  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Analytics Messages
# ---------------------------------------------------------------------------

class TestSignalGenerated:
    def test_inherits_message(self) -> None:
        sg = SignalGenerated(
            timestamp=_ts(), instrument_id=_inst(), direction=SignalDirection.BUY,
            strength=_price("0.85"), scanner_id="scanner-1",
        )
        assert isinstance(sg, RankMessage)

    def test_frozen(self) -> None:
        sg = SignalGenerated(
            timestamp=_ts(), instrument_id=_inst(), direction=SignalDirection.BUY,
            strength=_price("0.85"), scanner_id="scanner-1",
        )
        with pytest.raises(Exception):
            sg.direction = SignalDirection.SELL  # type: ignore[misc]


class TestScanCompleted:
    def test_inherits_message(self) -> None:
        sc = ScanCompleted(timestamp=_ts(), scanner_id="scanner-1", signal_count=5, universe_size=100)
        assert isinstance(sc, RankMessage)

    def test_frozen(self) -> None:
        sc = ScanCompleted(timestamp=_ts(), scanner_id="scanner-1", signal_count=5, universe_size=100)
        with pytest.raises(Exception):
            sc.signal_count = 0  # type: ignore[misc]


class TestBacktestCompleted:
    def test_inherits_message(self) -> None:
        bt = BacktestCompleted(
            timestamp=_ts(), strategy_id=_strategy(), metrics={"sharpe": 1.5}, trade_count=42,
        )
        assert isinstance(bt, RankMessage)

    def test_frozen(self) -> None:
        bt = BacktestCompleted(
            timestamp=_ts(), strategy_id=_strategy(), metrics={"sharpe": 1.5}, trade_count=42,
        )
        with pytest.raises(Exception):
            bt.trade_count = 0  # type: ignore[misc]


class TestRankingUpdated:
    def test_inherits_message(self) -> None:
        ru = RankingUpdated(timestamp=_ts(), universe="india_large", rankings=["RELIANCE", "TCS"])
        assert isinstance(ru, RankMessage)

    def test_frozen(self) -> None:
        ru = RankingUpdated(timestamp=_ts(), universe="india_large", rankings=["RELIANCE", "TCS"])
        with pytest.raises(Exception):
            ru.universe = ""  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Hierarchy sanity
# ---------------------------------------------------------------------------

class TestHierarchy:
    def test_all_market_data_inherit_market_data_message(self) -> None:
        for cls in (Quote, Trade, Bar, OrderBook, Tick):
            assert issubclass(cls, MarketDataMessage)
            assert issubclass(cls, Message)

    def test_all_order_messages_inherit_order_message(self) -> None:
        for cls in (OrderCommand, OrderPlaced, OrderFilled, OrderCancelled, OrderRejected, OrderModified):
            assert issubclass(cls, OrderMessage)
            assert issubclass(cls, Message)

    def test_all_portfolio_messages_inherit_portfolio_message(self) -> None:
        for cls in (PositionUpdated, AccountUpdated, PnLUpdated):
            assert issubclass(cls, PortfolioMessage)
            assert issubclass(cls, Message)

    def test_all_risk_messages_inherit_risk_message(self) -> None:
        for cls in (RiskCheckResult, RiskRejected, RiskAlert, AutoFlattenOrder):
            assert issubclass(cls, RiskMessage)
            assert issubclass(cls, Message)

    def test_all_system_messages_inherit_system_message(self) -> None:
        for cls in (
            Startup, Shutdown, ComponentHealth, ReconciliationDrift,
            ReconciliationCompleted, BrokerDisconnected, BrokerReconnected,
            ReplayStarted, ReplayCompleted, FeatureComputed,
        ):
            assert issubclass(cls, SystemMessage)
            assert issubclass(cls, Message)

    def test_all_analytics_messages_inherit_rank_message(self) -> None:
        for cls in (SignalGenerated, ScanCompleted, BacktestCompleted, RankingUpdated):
            assert issubclass(cls, RankMessage)
            assert issubclass(cls, Message)
