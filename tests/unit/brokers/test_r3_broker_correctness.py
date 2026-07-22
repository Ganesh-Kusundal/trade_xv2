"""R3: BrokerGateway instrument resolution and wire live gate."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from brokers.gateway import BrokerGateway
from brokers.providers.dhan.wire import DhanWireAdapter
from brokers.providers.upstox.wire import UpstoxWireAdapter
from brokers.session.broker_session import BrokerSession
from domain.enums import OrderType, ProductType, Side, Validity
from domain.exceptions import LiveBrokerBlockedError
from domain.instruments.instrument import Equity, Future
from domain.instruments.instrument_id import InstrumentId
from domain.orders.requests import OrderRequest
from domain.ports.broker_session_state import BrokerSessionState


def test_resolve_equity_by_exchange():
    equity = MagicMock(spec=Equity)
    universe = MagicMock()
    universe.equity.return_value = equity
    session = MagicMock()
    session.universe = universe
    runtime = MagicMock()
    gw = BrokerGateway(runtime, session)
    assert gw._resolve_instrument("RELIANCE", "NSE") is equity
    universe.equity.assert_called_once_with("RELIANCE", "NSE")


def test_resolve_derivative_via_canonical_id():
    future = MagicMock(spec=Future)
    iid = InstrumentId.future("NFO", "NIFTY", date(2026, 6, 30))
    universe = MagicMock()
    universe.get.return_value = future
    session = MagicMock()
    session.universe = universe
    gw = BrokerGateway(MagicMock(), session)
    result = gw._resolve_instrument(str(iid), "NFO")
    assert result is future
    universe.get.assert_called_once()
    universe.equity.assert_not_called()


def test_dhan_wire_place_order_blocked_without_gate():
    gw = DhanWireAdapter(MagicMock())
    req = OrderRequest(
        symbol="RELIANCE",
        exchange="NSE",
        transaction_type=Side.BUY,
        quantity=1,
        order_type=OrderType.MARKET,
        product_type=ProductType.INTRADAY,
        validity=Validity.DAY,
    )
    with pytest.raises(LiveBrokerBlockedError):
        gw.place_order(req)


def test_upstox_wire_place_order_blocked_without_gate():
    broker = MagicMock()
    gw = UpstoxWireAdapter(broker)
    req = OrderRequest(
        symbol="RELIANCE",
        exchange="NSE",
        transaction_type=Side.BUY,
        quantity=1,
        order_type=OrderType.MARKET,
        product_type=ProductType.INTRADAY,
        validity=Validity.DAY,
    )
    with pytest.raises(LiveBrokerBlockedError):
        gw.place_order(req)


def test_paper_session_degraded_when_health_probe_fails(monkeypatch):
    session = BrokerSession.__new__(BrokerSession)
    session._broker_id = "paper"
    session._session_state = BrokerSessionState.CONNECTED
    bad_gateway = MagicMock()
    bad_gateway.authenticate.return_value = False
    provider = MagicMock()
    provider.gateway = bad_gateway
    domain_session = MagicMock()
    domain_session.provider = provider
    domain_session.status = MagicMock(authenticated=True)
    session._session = domain_session
    assert session._probe_session_health() is False


def test_paper_history_prefers_datalake_over_synthetic(monkeypatch):
    monkeypatch.delenv("TRADEX_PAPER_SYNTHETIC_HISTORY", raising=False)
    from brokers.providers.paper.paper_gateway import PaperGateway

    import pandas as pd

    lake_df = pd.DataFrame(
        {
            "timestamp": [pd.Timestamp("2026-01-01")],
            "open": [100.0],
            "high": [101.0],
            "low": [99.0],
            "close": [100.5],
            "volume": [1000],
            "oi": [0],
            "symbol": ["RELIANCE"],
            "exchange": ["NSE"],
            "timeframe": ["1D"],
        }
    )
    monkeypatch.setattr(
        "datalake.gateway.DataLakeGateway.history",
        lambda *a, **k: lake_df,
    )
    gw = PaperGateway()
    df = gw.history("RELIANCE", timeframe="1D", lookback_days=5)
    assert len(df) == 1
    assert df["close"].iloc[0] == 100.5
