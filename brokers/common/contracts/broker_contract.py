from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any, ClassVar

import pandas as pd
import pytest

from brokers.common.core.connection import Capability
from brokers.common.core.domain import (
    FundLimits,
    Holding,
    Order,
    OrderResponse,
    OrderStatus,
    Position,
    Side,
    Trade,
)


class BrokerContractSuite:
    broker_name: ClassVar[str]

    @pytest.fixture
    def broker(self) -> Any:
        raise NotImplementedError("broker fixture must be provided by the broker implementation")

    def test_broker_name_is_contracted(self, broker: Any) -> None:
        assert broker.name == self.broker_name

    def test_broker_exposes_required_capabilities(self, broker: Any) -> None:
        assert broker.has_capability(Capability.MARKET_DATA)
        assert broker.has_capability(Capability.ORDER_COMMAND)
        assert broker.has_capability(Capability.ORDER_QUERY)
        assert broker.has_capability(Capability.PORTFOLIO)

    def test_broker_exposes_streaming_capability(self, broker: Any) -> None:
        """Broker should expose at least one streaming mechanism."""
        has_ws = broker.has_capability(Capability.WEBSOCKET)
        has_order_stream = broker.has_capability(Capability.ORDER_STREAM)
        assert has_ws or has_order_stream, "Broker must support WEBSOCKET or ORDER_STREAM"

    def test_broker_exposes_required_contract_methods(self, broker: Any) -> None:
        required_methods = (
            "get_quote",
            "get_historical_data",
            "get_option_chain",
            "place_order",
            "get_orders",
            "get_positions",
            "get_holdings",
            "get_fund_limits",
        )
        for method_name in required_methods:
            assert callable(getattr(broker, method_name))

    def test_order_status_normalization_contract(self) -> None:
        assert OrderStatus.normalize("EXECUTED") == OrderStatus.FILLED
        assert OrderStatus.normalize("COMPLETE") == OrderStatus.FILLED
        assert OrderStatus.normalize("TRANSIT") == OrderStatus.OPEN
        assert OrderStatus.normalize("TRIGGER PENDING") == OrderStatus.OPEN
        assert OrderStatus.normalize("PARTIALLY_EXECUTED") == OrderStatus.PARTIALLY_FILLED
        for status in OrderStatus:
            assert OrderStatus.normalize(status.value) == status

    # ── DataFrame Contract Tests ──────────────────────────────────────────

    def test_historical_data_schema(self, broker: Any) -> None:
        df = broker.get_historical_data("RELIANCE", "NSE", date(2026, 6, 1), date(2026, 6, 5), "1d")
        assert isinstance(df, pd.DataFrame)

        expected_columns = [
            "timestamp",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "oi",
            "symbol",
            "exchange",
            "timeframe",
        ]
        assert list(df.columns) == expected_columns

        # Check forbidden columns
        for col in ["security_id", "instrument_token", "exchange_token", "symbol_token"]:
            assert col not in df.columns

    def test_quote_schema(self, broker: Any) -> None:
        df = broker.get_quote("RELIANCE", "NSE")
        assert isinstance(df, pd.DataFrame)

        expected_columns = ["symbol", "exchange", "ltp", "bid", "ask", "volume", "oi", "timestamp"]
        assert list(df.columns) == expected_columns

        for col in ["security_id", "instrument_token", "exchange_token", "symbol_token"]:
            assert col not in df.columns

    def test_option_chain_schema(self, broker: Any) -> None:
        df = broker.get_option_chain("NIFTY", "NFO", "2026-07-30")
        assert isinstance(df, pd.DataFrame)

        expected_columns = [
            "underlying",
            "expiry",
            "strike",
            "option_type",
            "ltp",
            "bid",
            "ask",
            "volume",
            "oi",
            "iv",
            "delta",
            "gamma",
            "theta",
            "vega",
            "rho",
            "timestamp",
        ]
        assert list(df.columns) == expected_columns

        for col in ["security_id", "instrument_token", "exchange_token", "symbol_token"]:
            assert col not in df.columns

    def test_market_depth_schema(self, broker: Any) -> None:
        df = broker.get_market_depth("RELIANCE", "NSE")
        assert isinstance(df, pd.DataFrame)

        assert "symbol" in df.columns
        assert "timestamp" in df.columns
        for i in range(1, 21):
            assert f"bid_price_{i}" in df.columns
            assert f"bid_qty_{i}" in df.columns
            assert f"ask_price_{i}" in df.columns
            assert f"ask_qty_{i}" in df.columns

        for col in ["security_id", "instrument_token", "exchange_token", "symbol_token"]:
            assert col not in df.columns

    # ── Domain Object Contract Tests ──────────────────────────────────────

    def test_place_order(self, broker: Any) -> None:
        res = broker.place_order(
            "RELIANCE", "NSE", Side.BUY, 10, Decimal("2500"), "LIMIT", "CNC", "DAY"
        )
        assert isinstance(res, OrderResponse)
        assert res.success is True
        assert res.order_id  # non-empty order_id
        assert not hasattr(res, "security_id")

    def test_get_order(self, broker: Any) -> None:
        orders = broker.get_orders()
        assert len(orders) > 0
        target_id = orders[0].order_id
        o = broker.get_order(target_id)
        assert o is not None
        assert isinstance(o, Order)
        assert o.order_id
        assert o.symbol
        assert o.exchange
        assert isinstance(o.side, Side)
        assert isinstance(o.price, Decimal)
        assert o.quantity > 0
        assert not hasattr(o, "security_id")

    def test_get_orders(self, broker: Any) -> None:
        orders = broker.get_orders()
        assert isinstance(orders, list)
        for o in orders:
            assert isinstance(o, Order)
            assert not hasattr(o, "security_id")

    def test_get_positions(self, broker: Any) -> None:
        positions = broker.get_positions()
        assert isinstance(positions, list)
        for p in positions:
            assert isinstance(p, Position)
            assert not hasattr(p, "security_id")

    def test_get_holdings(self, broker: Any) -> None:
        holdings = broker.get_holdings()
        assert isinstance(holdings, list)
        for h in holdings:
            assert isinstance(h, Holding)
            assert not hasattr(h, "security_id")

    def test_get_fund_limits(self, broker: Any) -> None:
        funds = broker.get_fund_limits()
        assert isinstance(funds, FundLimits)
        assert funds.available_balance >= Decimal("0")
        assert not hasattr(funds, "security_id")

    def test_get_trades(self, broker: Any) -> None:
        trades = broker.get_trades()
        assert isinstance(trades, list)
        for t in trades:
            assert isinstance(t, Trade)
            assert not hasattr(t, "security_id")
