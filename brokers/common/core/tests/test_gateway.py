"""Gateway contract tests — validates the ultra-simple API."""

from __future__ import annotations

from decimal import Decimal

import pandas as pd
import pytest

from brokers.common.core.domain import (
    FundLimits,
    OrderResponse,
)
from brokers.gateway import Gateway
from brokers.paper import PaperBroker


@pytest.fixture
def gateway() -> Gateway:
    return Gateway(broker=PaperBroker(), auto_connect=True)


class TestGatewayLifecycle:
    def test_connect(self, gateway: Gateway) -> None:
        assert gateway._is_connected() is True

    def test_disconnect(self, gateway: Gateway) -> None:
        gateway.disconnect()
        assert gateway._is_connected() is False

    def test_reconnect(self, gateway: Gateway) -> None:
        assert gateway.reconnect() is True

    def test_health(self, gateway: Gateway) -> None:
        h = gateway.health()
        assert isinstance(h, dict)
        assert "broker" in h
        assert "connected" in h
        assert h["broker"] == "paper"

    def test_repr(self, gateway: Gateway) -> None:
        r = repr(gateway)
        assert "Gateway" in r
        assert "paper" in r

    def test_context_manager(self) -> None:
        with Gateway(broker=PaperBroker()) as g:
            assert g._is_connected() is True


class TestGatewayAccount:
    def test_funds(self, gateway: Gateway) -> None:
        funds = gateway.funds()
        assert isinstance(funds, FundLimits)
        assert funds.available_balance >= Decimal("0")

    def test_holdings(self, gateway: Gateway) -> None:
        holdings = gateway.holdings()
        assert isinstance(holdings, list)

    def test_positions(self, gateway: Gateway) -> None:
        positions = gateway.positions()
        assert isinstance(positions, list)

    def test_orders(self, gateway: Gateway) -> None:
        orders = gateway.orders()
        assert isinstance(orders, list)

    def test_trades(self, gateway: Gateway) -> None:
        trades = gateway.trades()
        assert isinstance(trades, list)

    def test_order_book(self, gateway: Gateway) -> None:
        assert isinstance(gateway.order_book(), list)

    def test_trade_book(self, gateway: Gateway) -> None:
        assert isinstance(gateway.trade_book(), list)


class TestGatewayMarketData:
    def test_ltp_single(self, gateway: Gateway) -> None:
        ltp = gateway.ltp("TCS")
        assert isinstance(ltp, float)
        assert ltp > 0

    def test_ltp_multiple(self, gateway: Gateway) -> None:
        result = gateway.ltp(["TCS", "INFY"])
        assert isinstance(result, dict)
        assert "TCS" in result
        assert "INFY" in result

    def test_quote_single(self, gateway: Gateway) -> None:
        df = gateway.quote("TCS")
        assert isinstance(df, pd.DataFrame)
        assert not df.empty
        assert "ltp" in df.columns

    def test_quote_multiple(self, gateway: Gateway) -> None:
        df = gateway.quote(["TCS", "INFY"])
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 2

    def test_history_default(self, gateway: Gateway) -> None:
        df = gateway.history("TCS")
        assert isinstance(df, pd.DataFrame)
        assert "timestamp" in df.columns
        assert "open" in df.columns
        assert "close" in df.columns

    def test_history_with_params(self, gateway: Gateway) -> None:
        df = gateway.history("TCS", timeframe="5m", lookback_days=30)
        assert isinstance(df, pd.DataFrame)

    def test_history_multi_symbol(self, gateway: Gateway) -> None:
        df = gateway.history(["TCS", "INFY"])
        assert isinstance(df, pd.DataFrame)

    def test_history_lazy(self, gateway: Gateway) -> None:
        try:
            import polars

            result = gateway.history("TCS", lazy=True)
            import polars as pl

            assert isinstance(result, pl.LazyFrame)
        except ImportError:
            result = gateway.history("TCS", lazy=True)
            assert isinstance(result, pd.DataFrame)

    def test_intraday(self, gateway: Gateway) -> None:
        df = gateway.intraday("TCS")
        assert isinstance(df, pd.DataFrame)

    def test_daily(self, gateway: Gateway) -> None:
        df = gateway.daily("TCS")
        assert isinstance(df, pd.DataFrame)

    def test_weekly(self, gateway: Gateway) -> None:
        df = gateway.weekly("TCS")
        assert isinstance(df, pd.DataFrame)

    def test_monthly(self, gateway: Gateway) -> None:
        df = gateway.monthly("TCS")
        assert isinstance(df, pd.DataFrame)


class TestGatewayDepth:
    def test_depth_default(self, gateway: Gateway) -> None:
        df = gateway.depth("TCS")
        assert isinstance(df, pd.DataFrame)
        assert "bid_price_1" in df.columns

    def test_depth_custom_levels(self, gateway: Gateway) -> None:
        df = gateway.depth("TCS", levels=3)
        assert isinstance(df, pd.DataFrame)

    def test_full_depth(self, gateway: Gateway) -> None:
        df = gateway.full_depth("TCS")
        assert isinstance(df, pd.DataFrame)


class TestGatewayOptions:
    def test_option_chain(self, gateway: Gateway) -> None:
        df = gateway.option_chain("NIFTY", expiry="2026-07-30")
        assert isinstance(df, pd.DataFrame)
        if not df.empty:
            assert "strike" in df.columns
            assert "option_type" in df.columns

    def test_ce(self, gateway: Gateway) -> None:
        df = gateway.ce("NIFTY", expiry="2026-07-30")
        assert isinstance(df, pd.DataFrame)
        if not df.empty:
            assert all(df["option_type"] == "CE")

    def test_pe(self, gateway: Gateway) -> None:
        df = gateway.pe("NIFTY", expiry="2026-07-30")
        assert isinstance(df, pd.DataFrame)
        if not df.empty:
            assert all(df["option_type"] == "PE")


class TestGatewayOrders:
    def test_buy(self, gateway: Gateway) -> None:
        resp = gateway.buy("TCS", qty=10)
        assert isinstance(resp, OrderResponse)
        assert resp.success is True
        assert resp.order_id

    def test_sell(self, gateway: Gateway) -> None:
        resp = gateway.sell("TCS", qty=10)
        assert isinstance(resp, OrderResponse)
        assert resp.success is True

    def test_market_buy(self, gateway: Gateway) -> None:
        resp = gateway.market_buy("TCS", qty=5)
        assert resp.success is True

    def test_market_sell(self, gateway: Gateway) -> None:
        resp = gateway.market_sell("TCS", qty=5)
        assert resp.success is True

    def test_limit_buy(self, gateway: Gateway) -> None:
        resp = gateway.limit_buy("TCS", qty=5, price=1000)
        assert resp.success is True

    def test_limit_sell(self, gateway: Gateway) -> None:
        resp = gateway.limit_sell("TCS", qty=5, price=1100)
        assert resp.success is True

    def test_cancel(self, gateway: Gateway) -> None:
        resp = gateway.buy("TCS", qty=1)
        cancel_resp = gateway.cancel(resp.order_id)
        assert isinstance(cancel_resp, OrderResponse)

    def test_basket(self, gateway: Gateway) -> None:
        results = gateway.basket(
            [
                {"symbol": "TCS", "qty": 1, "side": "BUY"},
                {"symbol": "INFY", "qty": 2, "side": "SELL"},
            ]
        )
        assert isinstance(results, list)
        assert len(results) == 2

    def test_cancel_all(self, gateway: Gateway) -> None:
        gateway.buy("TCS", qty=1)
        results = gateway.cancel_all()
        assert isinstance(results, list)


class TestGatewayPositionManagement:
    def test_close_no_position(self, gateway: Gateway) -> None:
        resp = gateway.close("TCS")
        assert resp.success is False

    def test_close_all_empty(self, gateway: Gateway) -> None:
        results = gateway.close_all()
        assert isinstance(results, list)
        assert len(results) == 0

    def test_exit_intraday_empty(self, gateway: Gateway) -> None:
        results = gateway.exit_intraday()
        assert isinstance(results, list)
        assert len(results) == 0


class TestGatewayInstruments:
    def test_search(self, gateway: Gateway) -> None:
        results = gateway.search("RELIANCE")
        assert isinstance(results, list)
        assert len(results) > 0

    def test_instrument(self, gateway: Gateway) -> None:
        instr = gateway.instrument("RELIANCE")
        assert instr is not None
        assert instr.symbol == "RELIANCE"

    def test_resolve(self, gateway: Gateway) -> None:
        info = gateway.resolve("RELIANCE")
        assert isinstance(info, dict)
        assert "symbol" in info
        assert "security_id" in info

    def test_universe(self, gateway: Gateway) -> None:
        nifty50 = gateway.universe("NIFTY50")
        assert isinstance(nifty50, list)
        assert len(nifty50) == 50
        assert "RELIANCE" in nifty50

    def test_universe_nifty100(self, gateway: Gateway) -> None:
        n100 = gateway.universe("NIFTY100")
        assert len(n100) == 100
        assert len(set(n100)) == 100

    def test_universe_nifty200(self, gateway: Gateway) -> None:
        n200 = gateway.universe("NIFTY200")
        assert len(set(n200)) == 200

    def test_universe_midcap50(self, gateway: Gateway) -> None:
        mid = gateway.universe("NIFTY_MIDCAP50")
        assert len(mid) == 50

    def test_multi_symbol_history_symbols(self, gateway: Gateway) -> None:
        df = gateway.history(["TCS", "INFY", "RELIANCE"])
        symbols = set(df["symbol"].unique())
        assert symbols == {"TCS", "INFY", "RELIANCE"}

    def test_exchange_column_canonical(self, gateway: Gateway) -> None:
        df = gateway.history("TCS")
        exchanges = df["exchange"].unique().tolist()
        assert "NSE_EQ" not in exchanges, f"Broker segment NSE_EQ leaked: {exchanges}"
        df = gateway.quote("TCS")
        exchanges = df["exchange"].unique().tolist()
        assert "NSE_EQ" not in exchanges, f"Broker segment NSE_EQ leaked in quote: {exchanges}"

    def test_depth_symbol_canonical(self, gateway: Gateway) -> None:
        for sym in ["RELIANCE", "INFY", "SBIN", "HDFCBANK"]:
            df = gateway.depth(sym)
            if not df.empty and "symbol" in df.columns:
                actual = df["symbol"].unique().tolist()
                assert actual == [sym], f"depth({sym}) leaked security_id: {actual}"

    def test_empty_list_inputs(self, gateway: Gateway) -> None:
        result = gateway.ltp([])
        assert result == {}
        df = gateway.quote([])
        assert isinstance(df, pd.DataFrame)
        assert df.empty
        df = gateway.history([])
        assert isinstance(df, pd.DataFrame)
        assert df.empty

    def test_strike_step_by_underlying(self) -> None:
        from brokers.gateway import _strike_step

        assert _strike_step("NIFTY") == 50
        assert _strike_step("BANKNIFTY") == 100
        assert _strike_step("FINNIFTY") == 50
        assert _strike_step("MIDCPNIFTY") == 25
        assert _strike_step("SENSEX") == 100
        assert _strike_step("UNKNOWN_STOCK") == 50  # default

    def test_dataframe_not_mutated(self, gateway: Gateway) -> None:
        q1 = gateway.quote("RELIANCE")
        q2 = gateway.quote("RELIANCE")
        assert q1 is not q2, "quote() should return a copy, not the same object"


class TestGatewayInputValidation:
    def test_buy_negative_qty(self, gateway: Gateway) -> None:
        with pytest.raises(ValueError, match="positive integer"):
            gateway.buy("TCS", qty=-5)

    def test_sell_zero_qty(self, gateway: Gateway) -> None:
        with pytest.raises(ValueError, match="positive integer"):
            gateway.sell("TCS", qty=0)

    def test_buy_float_qty(self, gateway: Gateway) -> None:
        with pytest.raises(ValueError, match="positive integer"):
            gateway.buy("TCS", qty=1.5)  # type: ignore

    def test_valid_qty(self, gateway: Gateway) -> None:
        resp = gateway.buy("TCS", qty=1)
        assert resp.success is True

    def test_disconnected_order_warns(self) -> None:
        g = Gateway(broker=PaperBroker(), auto_connect=False)
        # Should still work but log a warning (PaperBroker doesn't enforce connection)
        resp = g.buy("TCS", qty=1)
        assert resp.success is True


class TestGatewayOrderPriceValidation:
    """Regression: LIMIT/STOP_LOSS orders with zero prices must raise, not
    silently downgrade to MARKET. (Phase 0, Bug #5.)"""

    def test_limit_buy_with_zero_price_raises(self, gateway: Gateway) -> None:
        with pytest.raises(ValueError, match="LIMIT order for 'TCS' requires price > 0"):
            gateway.limit_buy("TCS", qty=1, price=0)

    def test_limit_sell_with_zero_price_raises(self, gateway: Gateway) -> None:
        with pytest.raises(ValueError, match="LIMIT order for 'TCS' requires price > 0"):
            gateway.limit_sell("TCS", qty=1, price=0)

    def test_stop_loss_with_zero_trigger_price_raises(self, gateway: Gateway) -> None:
        with pytest.raises(
            ValueError, match="STOP_LOSS order for 'TCS' requires trigger_price > 0"
        ):
            gateway.sl_buy("TCS", qty=1, trigger_price=0)

    def test_market_order_with_zero_price_succeeds(self, gateway: Gateway) -> None:
        # Market orders legitimately have no price; must NOT raise.
        resp = gateway.market_buy("TCS", qty=1)
        assert resp.success is True

    def test_limit_buy_with_valid_price_succeeds(self, gateway: Gateway) -> None:
        # Sanity: the new validation does not break the happy path.
        resp = gateway.limit_buy("TCS", qty=1, price=1500)
        assert resp.success is True


class TestGatewayDiagnostics:
    def test_rate_limits(self, gateway: Gateway) -> None:
        result = gateway.rate_limits()
        assert isinstance(result, dict)

    def test_status(self, gateway: Gateway) -> None:
        result = gateway.status()
        assert isinstance(result, dict)
        assert "broker" in result

    def test_connection_info(self, gateway: Gateway) -> None:
        result = gateway.connection_info()
        assert isinstance(result, dict)
        assert "broker" in result
        assert "connected" in result


class TestGatewayImport:
    def test_import_from_broker(self) -> None:
        from broker import Gateway as G

        assert G is Gateway

    def test_import_from_brokers(self) -> None:
        from brokers import Gateway as G

        assert G is Gateway
