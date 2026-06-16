"""Unified broker contract test suite — Upstox implementation.

Every test validates a contract that ANY broker adapter must satisfy.
Live tests use real Upstox API and are guarded by env var checks.
"""

from __future__ import annotations

import os
import sys
from decimal import Decimal
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))

from brokers.common.core.domain import MarketDepth, Quote
from brokers.upstox.gateway import UpstoxBrokerGateway

# ---------------------------------------------------------------------------
# Live-skip guard
# ---------------------------------------------------------------------------
ENV_PATH = Path(__file__).resolve().parent.parent.parent.parent.parent / ".env.upstox"
_live_env_loaded = False
if ENV_PATH.exists() and ENV_PATH.stat().st_size > 0:
    from dotenv import load_dotenv
    load_dotenv(ENV_PATH, override=True)
    # Only enable live tests if BOTH API key AND access token are present
    _live_env_loaded = bool(
        os.environ.get("UPSTOX_API_KEY") and os.environ.get("UPSTOX_ACCESS_TOKEN")
    )

def _should_skip_live() -> bool:
    """Skip live tests if credentials missing OR market is closed."""
    if not _live_env_loaded:
        return True
    from tests.market_hours import is_market_open
    return not is_market_open()

skip_live = pytest.mark.skipif(
    _should_skip_live(),
    reason="Live API tests require .env.upstox credentials and open market hours"
)


@pytest.fixture(scope="module")
def live_gateway() -> UpstoxBrokerGateway:
    from brokers.upstox.factory import UpstoxBrokerFactory
    gw = UpstoxBrokerFactory.create(env_path=ENV_PATH, load_instruments=True)
    yield gw
    gw.close()


@pytest.fixture(scope="module")
def mock_gateway():
    """Return a PaperGateway for contract testing without live credentials."""
    from brokers.paper.paper_gateway import PaperGateway
    return PaperGateway()


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
    @skip_live
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
        body = broker.historical_v2.get_candles(
            "NSE_EQ|INE002A01018", "day", to_d, from_d
        )
        assert body.get("status") == "success"
        candles = body.get("data", {}).get("candles", [])
        assert len(candles) > 0

    @skip_live
    def test_historical_v3_returns_candles(self, live_gateway):
        from datetime import date, timedelta
        broker = live_gateway._broker
        to_d = date.today()
        from_d = to_d - timedelta(days=5)
        body = broker.historical_v3.get_candles(
            "NSE_EQ|INE002A01018", "days", "1", to_d, from_d
        )
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
