"""Unified broker contract test suite — Upstox implementation.

Every test validates a contract that ANY broker adapter must satisfy.
Live tests use real Upstox API and are guarded by env var checks.
"""

from __future__ import annotations

import os
import sys
from decimal import Decimal

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))

from brokers.common.contracts.broker_contract import BrokerContractSuite
from brokers.providers.upstox.wire import UpstoxWireAdapter
from domain import MarketDepth, Quote
from tests.integration.brokers.upstox.conftest import ENV_PATH, skip_live, skip_live_market_hours

pytestmark = pytest.mark.live_readonly


@pytest.fixture(scope="module")
def mock_gateway():
    """Offline Upstox wire adapter with contract-test mocks wired."""
    from decimal import Decimal
    from unittest.mock import MagicMock

    from domain import Balance, Quote
    from tests.integration.fixtures.upstox import make_mock_broker

    mock_broker = make_mock_broker(ws_connected=False, allow_live_orders=False)
    gateway = UpstoxWireAdapter(mock_broker)
    gateway._market_data.quote = MagicMock(
        return_value=Quote(
            symbol="RELIANCE",
            ltp=Decimal("2550.00"),
            open=Decimal("2540.00"),
            high=Decimal("2560.00"),
            low=Decimal("2535.00"),
            close=Decimal("2545.00"),
            volume=500000,
        )
    )
    gateway._market_data.ltp = MagicMock(return_value=Decimal("2550.00"))
    gateway._portfolio.get_funds = MagicMock(
        return_value=Balance(
            available_balance=Decimal("100000.00"),
            used_margin=Decimal("0.00"),
        )
    )
    gateway._portfolio.get_positions = MagicMock(return_value=[])
    return gateway


class TestUpstoxSharedBrokerContract(BrokerContractSuite):
    """Canonical shared contract suite — offline mock gateway."""

    @pytest.fixture
    def gateway(self, mock_gateway):
        return mock_gateway


@pytest.fixture(scope="module")
def live_gateway() -> UpstoxWireAdapter:
    from infrastructure.gateway.factory import bootstrap_gateway

    result = bootstrap_gateway(
        "upstox",
        env_path=ENV_PATH,
        load_instruments=True,
        require_authenticated=True,
    )
    if not result.live_ready or result.gateway is None:
        pytest.skip(f"Upstox bootstrap failed: {result.error or result.status.value}")
    gw = result.gateway
    yield gw
    gw.close()


# ===========================================================================
# Contract Suite
# ===========================================================================


class TestUpstoxLTPContract:
    @skip_live
    def test_ltp_returns_decimal(self, live_gateway):
        ltp = live_gateway.ltp("RELIANCE", "NSE")
        assert isinstance(ltp, Decimal)
        assert ltp > 0

    @skip_live
    def test_ltp_multiple_symbols(self, live_gateway):
        for sym in ["RELIANCE", "INFY", "TCS"]:
            ltp = live_gateway.ltp(sym, "NSE")
            assert ltp > 0, f"LTP for {sym} should be positive"


class TestUpstoxQuoteContract:
    @skip_live
    def test_quote_has_required_fields(self, live_gateway):
        q = live_gateway.quote("RELIANCE", "NSE")
        assert isinstance(q, Quote)
        assert q.ltp > 0
        assert q.open > 0
        assert q.high > 0
        assert q.low > 0


class TestUpstoxDepthContract:
    @skip_live_market_hours
    def test_depth_returns_bids_and_asks(self, live_gateway):
        depth = live_gateway.depth("RELIANCE", "NSE")
        assert isinstance(depth, MarketDepth)
        assert isinstance(depth.bids, list)
        assert isinstance(depth.asks, list)


class TestUpstoxPortfolioContract:
    @skip_live
    def test_holdings_returns_list(self, live_gateway):
        holdings = live_gateway.holdings()
        assert isinstance(holdings, list)

    @skip_live
    def test_positions_returns_list(self, live_gateway):
        positions = live_gateway.positions()
        assert isinstance(positions, list)


class TestUpstoxFundsContract:
    @skip_live
    def test_funds_returns_balance(self, live_gateway):
        funds = live_gateway.funds()
        assert hasattr(funds, "available_balance")
        assert isinstance(funds.available_balance, Decimal)


class TestUpstoxOrdersContract:
    @skip_live
    def test_order_list_returns_list(self, live_gateway):
        broker = live_gateway._broker
        orders = broker.order_query.get_order_list()
        assert isinstance(orders, list)

    @skip_live
    def test_trades_returns_list(self, live_gateway):
        broker = live_gateway._broker
        trades = broker.order_query.get_trades()
        assert isinstance(trades, list)


class TestUpstoxHistoricalContract:
    @skip_live
    def test_historical_v2_returns_candles(self, live_gateway):
        from datetime import date, timedelta

        broker = live_gateway._broker
        to_d = date.today()
        from_d = to_d - timedelta(days=5)
        body = broker.historical_v2.get_candles("NSE_EQ|INE002A01018", "day", to_d, from_d)
        assert body.get("status") == "success"
        candles = body.get("data", {}).get("candles", [])
        assert len(candles) > 0

    @skip_live
    def test_historical_v3_returns_candles(self, live_gateway):
        from datetime import date, timedelta

        broker = live_gateway._broker
        to_d = date.today()
        from_d = to_d - timedelta(days=5)
        body = broker.historical_v3.get_candles("NSE_EQ|INE002A01018", "days", "1", to_d, from_d)
        assert body.get("status") == "success"
        candles = body.get("data", {}).get("candles", [])
        assert len(candles) > 0


class TestUpstoxMarketStatusContract:
    @skip_live
    def test_market_status_returns_data(self, live_gateway):
        import requests

        broker = live_gateway._broker
        token = broker.settings.access_token
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        r = requests.get("https://api.upstox.com/v2/market/status/NSE", headers=headers, timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert data.get("status") == "success"


class TestUpstoxInstrumentResolverWiring:
    """``UpstoxOptionsAdapter``/``UpstoxFuturesClient`` were constructed
    without ``instrument_resolver`` in ``broker.py``'s ``_build_adapters``/
    ``_build_raw_clients``, even though ``self.instrument_resolver`` was
    available at construction time and passed to sibling adapters
    (``order_query``, ``slice``). This left ``option_chain``/``future_chain``
    permanently broken with "Upstox instruments not loaded", regardless of
    whether instruments were actually loaded — regression guard for that."""

    def test_options_adapter_has_resolver_wired(self, live_gateway):
        broker = live_gateway._broker
        assert broker.options._resolver is not None
        assert broker.options._resolver is broker.instrument_resolver

    def test_futures_client_has_resolver_wired(self, live_gateway):
        broker = live_gateway._broker
        assert broker.futures_client._resolver is not None
        assert broker.futures_client._resolver is broker.instrument_resolver

    @skip_live
    def test_option_chain_works_for_nfo(self, live_gateway):
        chain = live_gateway.option_chain("NIFTY", "NFO")
        assert chain.strikes, "expected at least one strike"

    @skip_live
    def test_future_chain_works_for_nfo(self, live_gateway):
        chain = live_gateway.future_chain("NIFTY", "NFO")
        assert chain.contracts, "expected at least one future contract"

    @skip_live
    def test_future_chain_works_for_mcx(self, live_gateway):
        chain = live_gateway.future_chain("GOLD", "MCX")
        assert chain.contracts, "expected at least one future contract"


class TestUpstoxMcxBareSymbolResolution:
    """MCX instrument records leave ``symbol`` blank (only ``trading_symbol``
    is populated), so a bare underlying like "CRUDEOIL" doesn't match the
    resolver's dict directly. The commodity is often cross-listed under both
    MCX_FO and NSE_COM with identical trading_symbol/expiry, so naively
    picking any matching future risks silently returning an NSE_COM
    contract (no MCX market data => LTP always 0). Regression guard for
    resolve_instrument_key() deterministically picking the near-month
    MCX_FO future for a bare commodity symbol."""

    @skip_live
    @pytest.mark.parametrize("symbol", ["GOLD", "CRUDEOIL", "SILVER"])
    def test_ltp_nonzero_for_bare_commodity_symbol(self, live_gateway, symbol):
        ltp = live_gateway.ltp(symbol, "MCX")
        assert ltp > 0, f"{symbol} LTP should be a real, positive price"

    def test_resolved_key_is_mcx_segment(self, live_gateway):
        broker = live_gateway._broker
        key = broker.instruments.resolve_instrument_key("CRUDEOIL", "MCX")
        assert key.startswith("MCX_FO|"), f"expected an MCX_FO instrument_key, got {key!r}"


class TestUpstoxOptionsContract:
    @skip_live
    def test_option_chain_returns_data(self, live_gateway):
        import requests

        broker = live_gateway._broker
        token = broker.settings.access_token
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        r = requests.get(
            "https://api.upstox.com/v2/option/chain?instrument_key=NSE_INDEX|Nifty%2050&expiry_date=2026-06-19",
            headers=headers,
            timeout=10,
        )
        assert r.status_code == 200
        data = r.json()
        assert data.get("status") == "success"
