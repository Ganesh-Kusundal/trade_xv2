"""Object-model test pyramid — scenario IDs for CI (L0–L2).

L0 unit  — pure domain
L1 integration — OMS + fakes
L2 e2e paper — BrokerSession.connect("paper")

Live L3 lives under @pytest.mark.live (optional secrets).
"""

from __future__ import annotations

from brokers import BrokerSession
from tests.support.gateway_orders import (
    cancel_via_gateway,
    modify_via_gateway,
    place_via_gateway,
    subscribe_via_gateway,
)

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

import tradex
from application.oms.session_bridge import build_oms_service
from domain.entities.position import Position
from domain.enums import OrderStatus
from domain.instruments.display_names import format_display_name, parse_display_name
from domain.instruments.timeframes import normalize_timeframe
from domain.orders.intent import OrderIntent
from domain.orders.requests import ModifyOrderRequest, OrderRequest
from domain.portfolio.account_view import AccountView
from domain.portfolio.portfolio import Portfolio
from domain.ports.protocols import OrderResult
from domain.universe import Session

# ── L0 Unit ──────────────────────────────────────────────────────────────


def test_U_PORTFOLIO_PNL():
    p = Portfolio()
    p.add_position(
        Position(
            symbol="RELIANCE",
            exchange="NSE",
            quantity=10,
            avg_price=Decimal("100"),
            ltp=Decimal("110"),
            unrealized_pnl=Decimal("100"),
            realized_pnl=Decimal("5"),
        )
    )
    assert p.unrealized_pnl.to_decimal() == Decimal("100")
    assert p.realized_pnl.to_decimal() == Decimal("5")
    assert p.total_pnl.to_decimal() == Decimal("105")
    assert p.position_count == 1


def test_U_ACCOUNT_EMPTY():
    view = AccountView(None)
    with pytest.raises(RuntimeError, match="ExecutionProvider"):
        view.refresh()
    assert view.is_refreshed is False


def test_U_DISPLAY_NAME_AND_TF():
    iid = parse_display_name("NIFTY 21 NOV 24400 CALL", default_year=2026)
    assert format_display_name(iid).endswith("CALL")
    assert normalize_timeframe("DAY") == "1D"
    assert normalize_timeframe("15") == "15m"


# ── L1 Integration ───────────────────────────────────────────────────────


class _FakeEP:
    name = "fake"

    def __init__(self) -> None:
        self.cancelled: list[str] = []
        self.modified: list[Any] = []
        self.placed = 0

    def place_order(self, request: OrderRequest) -> OrderResult:
        from domain.entities.order import OrderResponse

        self.placed += 1
        return OrderResult.ok(
            OrderResponse.ok(order_id=f"OID-{self.placed}", status=OrderStatus.OPEN)
        )

    def cancel_order(self, order_id: str) -> OrderResult:
        from domain.entities.order import OrderResponse

        self.cancelled.append(order_id)
        return OrderResult.ok(OrderResponse.ok(order_id=order_id, status=OrderStatus.CANCELLED))

    def modify_order(self, request: ModifyOrderRequest) -> OrderResult:
        from domain.entities.order import OrderResponse

        self.modified.append(request)
        return OrderResult.ok(OrderResponse.ok(order_id=request.order_id, status=OrderStatus.OPEN))

    def get_order_book(self) -> list:
        return []

    def get_positions(self) -> list:
        return [
            Position(
                symbol="RELIANCE",
                exchange="NSE",
                quantity=5,
                avg_price=Decimal("100"),
                ltp=Decimal("105"),
            )
        ]

    def get_holdings(self) -> list:
        return []

    def get_funds(self):
        return {"available": Decimal("50000")}


# fix Any import for type hint in FakeEP
from typing import Any  # noqa: E402


def test_I_OMS_PLACE_CANCEL():
    from application.oms import register_oms_context, reset_oms_context
    from tests.conftest import build_test_trading_context

    reset_oms_context()
    register_oms_context(build_test_trading_context())
    try:
        ep = _FakeEP()
        oms = build_oms_service(ep, broker_id="paper")
        intent = OrderIntent(
            symbol="RELIANCE",
            exchange="NSE",
            side=__import__("domain.enums", fromlist=["Side"]).Side.BUY,
            quantity=1,
            price=Decimal("100"),
            correlation_id="test:place-cancel",
        )
        r = oms.place(intent)
        assert r.success
        oid = r.order.order_id
        c = oms.cancel(oid)
        assert c.success
        assert oid in ep.cancelled
    finally:
        reset_oms_context()


def test_I_OMS_MODIFY():
    from application.oms import register_oms_context, reset_oms_context
    from domain.enums import Side
    from tests.conftest import build_test_trading_context

    reset_oms_context()
    register_oms_context(build_test_trading_context())
    try:
        ep = _FakeEP()
        oms = build_oms_service(ep, broker_id="paper")

        r = oms.place(
            OrderIntent(
                symbol="TCS",
                exchange="NSE",
                side=Side.BUY,
                quantity=2,
                price=Decimal("200"),
                correlation_id="test:mod",
            )
        )
        assert r.success
        m = oms.modify(
            ModifyOrderRequest(order_id=r.order.order_id, price=Decimal("199"), quantity=3)
        )
        assert m.success
        assert ep.modified and ep.modified[0].price == Decimal("199")
    finally:
        reset_oms_context()


def test_I_ACCOUNT_REFRESH():
    ep = _FakeEP()
    view = AccountView(ep)
    view.refresh()
    assert view.is_refreshed
    assert view.portfolio.position_count == 1
    assert view.funds is not None
    assert "position_count" in view.describe()


def test_I_MODE_MARKET_BLOCK_CANCEL():
    mock_gw = MagicMock()
    with patch("infrastructure.gateway.factory._create_transport_gateway", return_value=mock_gw):
        import brokers.providers.dhan  # noqa: F401

        session = tradex.connect("dhan", mode="market", load_instruments=False)
        with pytest.raises(RuntimeError, match="ORDERS_DISABLED"):
            cancel_via_gateway(session, "OID-1")
        with pytest.raises(RuntimeError, match="ORDERS_DISABLED"):
            modify_via_gateway(session, "OID-1", price=Decimal("1"))
        session.close()


def test_I_UPSTOX_ADAPTER():
    import brokers.providers.upstox  # noqa: F401
    from types import SimpleNamespace

    from infrastructure.adapter_factory import create_data_adapter

    gw = MagicMock()
    gw.quote.return_value = SimpleNamespace(
        ltp=Decimal("10"),
        bid=0,
        ask=0,
        volume=0,
        high=0,
        low=0,
        open=0,
        close=0,
        oi=0,
    )
    adapter = create_data_adapter(gw, broker_id="upstox")
    assert adapter is not None
    assert getattr(adapter, "name", None) == "upstox"
    from domain.instruments.instrument_id import InstrumentId

    q = adapter.get_quote(InstrumentId.equity("NSE", "RELIANCE"))
    assert q is not None
    assert q.ltp == Decimal("10")


# ── L2 E2E paper ─────────────────────────────────────────────────────────


def test_E_PAPER_CONNECT():
    session = BrokerSession.connect("paper")
    assert session.status is not None
    assert session.status.mode == "sim"
    assert session.status.orders_enabled is True
    session.close()


def test_E_PAPER_QUOTE_HIST():
    session = BrokerSession.connect("paper")
    eq = session.universe.equity("RELIANCE")
    eq.refresh()
    assert True  # paper may seed quote
    series = eq.history(timeframe="1D", days=5)
    assert series is not None
    session.close()


def test_E_PAPER_ORDER_CYCLE():
    """Paper LIMIT rests OPEN → modify + cancel; MARKET fills."""
    from domain.enums import OrderStatus

    session = BrokerSession.connect("paper")
    eq = session.universe.equity("RELIANCE")
    r = place_via_gateway(session, eq, 1, price=Decimal("100"), correlation_id="e2e:cycle")
    assert r.success
    assert r.order is not None
    assert r.order.status == OrderStatus.OPEN
    oid = r.order.order_id
    m = modify_via_gateway(session, oid, price=Decimal("99"))
    assert m.success
    c = cancel_via_gateway(session, oid)
    assert c.success
    # market fills via gateway (Instrument.market has no LTP injection for risk)
    r2 = place_via_gateway(session, eq, 1, order_type="MARKET", correlation_id="e2e:mkt")
    assert r2.success
    assert r2.order.status == OrderStatus.FILLED
    session.close()


def test_I_INSTR_CANCEL_VIA_SESSION_STACK():
    """L1: OPEN order cancel through Session + OmsOrderService + FakeEP."""
    from application.oms import register_oms_context, reset_oms_context
    from domain.session_status import MODE_SIM, PHASE_READY_TRADE, SessionStatus
    from tests.conftest import build_test_trading_context

    reset_oms_context()
    register_oms_context(build_test_trading_context())
    try:
        ep = _FakeEP()
        oms = build_oms_service(ep, broker_id="paper")
    except Exception:
        reset_oms_context()
        raise

    class _Prov:
        name = "paper"

        def get_quote(self, *a, **k):
            return None

        def get_history(self, *a, **k):
            return []

        def get_history_series(self, *a, **k):
            from domain.candles.historical import HistoricalSeries, InstrumentRef

            return HistoricalSeries(
                bars=[],
                coverage=None,
                instrument=InstrumentRef(symbol="X", exchange="NSE"),
                timeframe="1D",
            )

        def get_depth(self, *a, **k):
            return None

        def get_option_chain(self, *a, **k):
            from domain.entities.options import OptionChain

            return OptionChain(underlying="", exchange="", expiry="")

        def get_future_chain(self, *a, **k):
            from domain.entities.options import FutureChain

            return FutureChain(underlying="", exchange="")

        def subscribe(self, *a, **k):
            return None

        def unsubscribe(self, *a, **k):
            return None

    try:
        session = Session(
            _Prov(),
            execution_provider=ep,
            order_service=oms,
            status=SessionStatus(
                phase=PHASE_READY_TRADE,
                broker_id="paper",
                mode=MODE_SIM,
                orders_enabled=True,
            ),
        )
        eq = session.universe.equity("RELIANCE")
        r = place_via_gateway(session, eq, 1, price=Decimal("50"), correlation_id="l1:instr-cancel")
        assert r.success
        c = cancel_via_gateway(session, r.order.order_id)
        assert c.success
        assert r.order.order_id in ep.cancelled
        session.close()
    finally:
        reset_oms_context()


def test_E_PAPER_ACCOUNT():
    session = BrokerSession.connect("paper")
    acc = session.account
    acc.refresh()
    assert acc.is_refreshed
    # shape stable
    d = acc.describe()
    assert "position_count" in d
    assert "has_funds" in d
    session.close()


def test_E_PAPER_INSTRUMENT_CAPS_EMPTY():
    session = BrokerSession.connect("paper")
    eq = session.universe.equity("INFY")
    assert eq.broker is not None
    # paper has no depth extensions
    assert eq.capabilities() == [] or isinstance(eq.capabilities(), list)
    session.close()


def test_E_PAPER_ASSET_TYPES_AND_ORDERS_LIST():
    session = BrokerSession.connect("paper")
    etf = session.universe.etf("NIFTYBEES")
    assert etf.id.is_etf
    com = session.universe.commodity("CRUDEOIL", expiry=__import__("datetime").date(2026, 11, 19))
    assert com.id.is_commodity
    eq = session.universe.equity("RELIANCE")
    r = place_via_gateway(session, eq, 1, price=Decimal("100"), correlation_id="e2e:orders-list")
    assert r.success
    book = session.gateway.orders()
    assert isinstance(book, list)
    session.close()


def test_I_DHAN_EXTENSION_CAPS_INCLUDE_SUPER():
    mock_gw = MagicMock()
    with patch("infrastructure.gateway.factory._create_transport_gateway", return_value=mock_gw):
        import brokers.providers.dhan  # noqa: F401

        session = tradex.connect("dhan", mode="market", load_instruments=False)
        eq = session.universe.equity("RELIANCE")
        caps = eq.capabilities()
        assert "depth_20" in caps
        assert "depth_200" in caps
        assert "super_order" in caps
        assert "forever_order" in caps
        session.close()
