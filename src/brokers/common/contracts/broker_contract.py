"""BrokerContractSuite — tests that verify any MarketDataGateway implementation
conforms to the frozen v1.0 contract.

Usage: subclass this in each broker's contract test directory and provide
a ``gateway`` fixture that returns a configured MarketDataGateway instance.

The method names tested here match the actual MarketDataGateway ABC
(quote, history, option_chain, etc.), not legacy names (get_quote, etc.).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pandas as pd
import pytest

from brokers.common.broker_capabilities import BrokerCapabilities
from domain import (
    Balance,
    DepthLevel,
    MarketDepth,
    OrderStatus,
    Quote,
)
from domain.ports.broker_adapter import BrokerAdapter as MarketDataGateway
from domain.market_enums import ExchangeId


class BrokerContractSuite:
    """Contract tests for any MarketDataGateway implementation.

    Subclasses must provide a ``gateway`` fixture returning a
    configured MarketDataGateway instance.
    """

    @pytest.fixture
    def gateway(self) -> MarketDataGateway:
        raise NotImplementedError("gateway fixture must be provided by the broker implementation")

    # ── Lifecycle ─────────────────────────────────────────────────────────

    def test_gateway_is_market_data_gateway(self, gateway: Any) -> None:
        # Structural port surface (runtime Protocol isinstance is brittle across
        # paper/live facades that satisfy the port without explicit subclassing).
        required = ("quote", "history", "positions", "funds", "describe")
        missing = [name for name in required if not hasattr(gateway, name)]
        assert not missing, f"gateway missing port methods: {missing}"
        if isinstance(gateway, type):
            pytest.fail("gateway fixture must return an instance, not a class")

    def test_describe_returns_dict(self, gateway: Any) -> None:
        result = gateway.describe()
        assert isinstance(result, dict)
        assert "broker" in result

    def test_capabilities_returns_broker_capabilities(self, gateway: Any) -> None:
        caps = gateway.capabilities()
        assert isinstance(caps, BrokerCapabilities)

    def test_capabilities_declare_market_surfaces(self, gateway: Any) -> None:
        caps = gateway.capabilities()
        assert caps.market_surfaces, "broker must declare market_surfaces"
        for surface in caps.market_surfaces:
            assert caps.serves(surface.asset_kind, surface.exchange), (
                f"declared surface not served: {surface}"
            )

    def test_port_methods_do_not_return_raw_wire_dicts(self, gateway: Any) -> None:
        """Port methods must return domain entities, not raw ``{\"data\": ...}`` envelopes."""
        quote = gateway.quote("RELIANCE", "NSE")
        assert not isinstance(quote, dict), "quote() must not return a raw dict"
        assert isinstance(quote, Quote)

        funds = gateway.funds()
        assert not isinstance(funds, dict), "funds() must not return a raw dict"
        assert isinstance(funds, Balance)

        positions = gateway.positions()
        assert isinstance(positions, list)
        assert not (positions and isinstance(positions[0], dict) and "data" in positions[0])

    # ── Market Data ───────────────────────────────────────────────────────

    def test_quote_returns_quote(self, gateway: Any) -> None:
        result = gateway.quote("RELIANCE", "NSE")
        assert isinstance(result, Quote)
        assert result.symbol == "RELIANCE"
        assert isinstance(result.ltp, Decimal)

    def test_ltp_returns_decimal(self, gateway: Any) -> None:
        result = gateway.ltp("RELIANCE", "NSE")
        assert isinstance(result, Decimal)
        assert result >= Decimal("0")

    def test_depth_returns_market_depth(self, gateway: Any) -> None:
        result = gateway.depth("RELIANCE", "NSE")
        assert isinstance(result, MarketDepth)
        assert result.bids is not None
        assert result.asks is not None
        if result.bids:
            assert isinstance(result.bids[0], DepthLevel)

    def test_history_returns_dataframe(self, gateway: Any) -> None:
        df = gateway.history("RELIANCE", "NSE", "1D", lookback_days=5)
        assert isinstance(df, pd.DataFrame)
        if not df.empty:
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
            for col in expected_columns:
                assert col in df.columns, f"Missing column: {col}"
            for col in ["security_id", "instrument_token", "exchange_token"]:
                assert col not in df.columns, f"Forbidden column: {col}"

    def test_option_chain_returns_dict(self, gateway: Any) -> None:
        from domain.entities.options import OptionChain

        result = gateway.option_chain("NIFTY", "NFO")
        # Accept both domain objects and dict representations (broker flexibility)
        if isinstance(result, OptionChain):
            result = result.to_dict()
        assert isinstance(result, dict)
        assert "underlying" in result

    def test_future_chain_returns_dict(self, gateway: Any) -> None:
        from domain.entities.options import FutureChain

        result = gateway.future_chain("NIFTY", "NFO")
        if isinstance(result, FutureChain):
            result = result.to_dict()
        assert isinstance(result, dict)
        assert "underlying" in result

    # ── Trading ───────────────────────────────────────────────────────────

    def test_get_orderbook_returns_list(self, gateway: Any) -> None:
        result = gateway.get_orderbook()
        assert isinstance(result, list)

    def test_get_trade_book_returns_list(self, gateway: Any) -> None:
        result = gateway.get_trade_book()
        assert isinstance(result, list)

    # ── Portfolio ─────────────────────────────────────────────────────────

    def test_positions_returns_list(self, gateway: Any) -> None:
        result = gateway.positions()
        assert isinstance(result, list)

    def test_holdings_returns_list(self, gateway: Any) -> None:
        result = gateway.holdings()
        assert isinstance(result, list)

    def test_funds_returns_balance(self, gateway: Any) -> None:
        result = gateway.funds()
        assert isinstance(result, Balance)
        assert result.available_balance >= Decimal("0")

    def test_trades_returns_list(self, gateway: Any) -> None:
        result = gateway.trades()
        assert isinstance(result, list)

    # ── Instrument ────────────────────────────────────────────────────────

    def test_search_returns_list(self, gateway: Any) -> None:
        result = gateway.search("RELIANCE")
        assert isinstance(result, list)

    # ── Order Status Normalization ────────────────────────────────────────

    def test_order_status_normalization_contract(self) -> None:
        assert OrderStatus.normalize("EXECUTED") == OrderStatus.FILLED
        assert OrderStatus.normalize("COMPLETE") == OrderStatus.FILLED
        assert OrderStatus.normalize("TRANSIT") == OrderStatus.OPEN
        assert OrderStatus.normalize("TRIGGER PENDING") == OrderStatus.OPEN
        assert OrderStatus.normalize("PARTIALLY_EXECUTED") == OrderStatus.PARTIALLY_FILLED
        for status in OrderStatus:
            assert OrderStatus.normalize(status.value) == status

    def test_orderbook_entries_use_typed_order_status(self, gateway: Any) -> None:
        """When the orderbook is non-empty, every entry's status must be OrderStatus."""
        book = gateway.get_orderbook()
        assert isinstance(book, list)
        for order in book:
            status = getattr(order, "order_status", None) or getattr(order, "status", None)
            if status is None:
                continue
            assert isinstance(status, OrderStatus), (
                f"order_status must be OrderStatus enum, got {type(status).__name__}: {status!r}"
            )

    # ── Observability ────────────────────────────────────────────────────

    def test_connection_status_returns_dict(self, gateway: Any) -> None:
        if not hasattr(gateway, "get_connection_status"):
            pytest.skip("optional observability: get_connection_status")
        result = gateway.get_connection_status()
        assert isinstance(result, dict)

    def test_token_refresh_metrics_returns_dict(self, gateway: Any) -> None:
        if not hasattr(gateway, "get_token_refresh_metrics"):
            pytest.skip("optional observability: get_token_refresh_metrics")
        result = gateway.get_token_refresh_metrics()
        assert isinstance(result, dict)
        assert "refresh_count" in result

    def test_rate_limiter_metrics_returns_dict(self, gateway: Any) -> None:
        if not hasattr(gateway, "get_rate_limiter_metrics"):
            pytest.skip("optional observability: get_rate_limiter_metrics")
        result = gateway.get_rate_limiter_metrics()
        assert isinstance(result, dict)
        assert "tokens_available" in result

    # ── Authentication / lifecycle ─────────────────────────────────────────

    def test_authenticate_or_connected(self, gateway: Any) -> None:
        if hasattr(gateway, "authenticate"):
            assert gateway.authenticate() in (True, False)
            return
        assert getattr(gateway, "is_connected", True) is True

    def test_describe_returns_dict_when_available(self, gateway: Any) -> None:
        if not hasattr(gateway, "describe"):
            pytest.skip("optional: describe()")
        result = gateway.describe()
        assert isinstance(result, dict)

    # ── Order lifecycle (when execution surface present) ───────────────────

    def test_place_order_when_supported(self, gateway: Any) -> None:
        if not hasattr(gateway, "place_order"):
            pytest.skip("gateway has no place_order")
        from domain.orders.requests import OrderRequest
        from domain.types import Side

        request = OrderRequest(
            symbol="RELIANCE",
            exchange=ExchangeId.NSE,
            transaction_type=Side.BUY,
            quantity=1,
            order_type="LIMIT",
            price=1,
        )
        quota = getattr(gateway, "quota_token", None)
        if quota is not None:
            result = gateway.place_order(request, quota=quota)
        else:
            result = gateway.place_order(
                symbol="RELIANCE",
                exchange=ExchangeId.NSE,
                side="BUY",
                quantity=1,
                price=1,
                order_type="LIMIT",
            )
        assert result is not None

    def test_cancel_order_when_supported(self, gateway: Any) -> None:
        if not hasattr(gateway, "cancel_order"):
            pytest.skip("gateway has no cancel_order")
        quota = getattr(gateway, "quota_token", None)
        if quota is not None:
            gateway.cancel_order("test-order-id", quota=quota)
        else:
            gateway.cancel_order("test-order-id")

    def test_modify_order_when_supported(self, gateway: Any) -> None:
        if not hasattr(gateway, "modify_order"):
            pytest.skip("gateway has no modify_order")
        quota = getattr(gateway, "quota_token", None)
        if quota is not None:
            from domain.orders.requests import ModifyOrderRequest

            gateway.modify_order(
                ModifyOrderRequest(order_id="test-order-id", quantity=1), quota=quota
            )
        else:
            gateway.modify_order("test-order-id", quantity=1)
