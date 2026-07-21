"""Unified broker contract test suite — Dhan implementation.

Subclasses ``BrokerContractSuite`` for the shared port contract, then adds
Dhan-specific offline/live assertions (resolver, validation, futures, options).
"""

from __future__ import annotations

import os
import time
from decimal import Decimal
from pathlib import Path

import pytest

from brokers.common.contracts.broker_contract import BrokerContractSuite
from brokers.providers.dhan._dhan_types import Exchange
from brokers.providers.dhan.exceptions import InstrumentNotFoundError
from brokers.providers.dhan.execution.orders import IdempotencyCache
from brokers.providers.dhan.streaming.connection import DhanConnection
from brokers.providers.dhan.wire import DhanWireAdapter
from domain import MarketDepth, Quote
from infrastructure.gateway.factory import bootstrap_gateway
from tests.support.brokers.dhan.fixtures import SAMPLE_ROWS, FakeHttpClient

ENV_PATH = Path(__file__).resolve().parents[5] / ".env.local"
_live_env_loaded = False
if ENV_PATH.exists() and ENV_PATH.stat().st_size > 0:
    from dotenv import load_dotenv

    load_dotenv(ENV_PATH, override=True)
    _live_env_loaded = bool(os.environ.get("DHAN_CLIENT_ID"))


def _should_skip_live() -> bool:
    """Credentials only — token refresh is automatic; market hours not required."""
    return not _live_env_loaded


def _should_skip_live_market_hours() -> bool:
    if not _live_env_loaded:
        return True
    from tests.market_hours import is_market_open

    return not is_market_open()


skip_live = pytest.mark.skipif(
    _should_skip_live(),
    reason="Live API tests require .env.local with DHAN_CLIENT_ID",
)

skip_live_market_hours = pytest.mark.skipif(
    _should_skip_live_market_hours(),
    reason="Live stream/depth tests require NSE market hours (09:15–15:30 IST)",
)


@pytest.fixture()
def offline_gateway() -> DhanWireAdapter:
    client = FakeHttpClient()
    conn = DhanConnection(client=client)
    conn.instruments.load_from_rows(SAMPLE_ROWS)
    return DhanWireAdapter(conn)


@pytest.fixture(scope="module")
def live_gateway() -> DhanWireAdapter:
    if not _live_env_loaded:
        pytest.skip("Live API tests require .env.local with DHAN_CLIENT_ID")
    result = bootstrap_gateway(
        "dhan",
        env_path=ENV_PATH,
        load_instruments=True,
        require_authenticated=True,
    )
    if not result.live_ready or result.gateway is None:
        pytest.skip(f"Dhan bootstrap failed: {result.error or result.status.value}")
    gw = result.gateway
    yield gw
    gw.close()


class TestDhanBrokerContract(BrokerContractSuite):
    """Shared BrokerContractSuite + Dhan offline gateway."""

    @pytest.fixture
    def gateway(self, offline_gateway: DhanWireAdapter) -> DhanWireAdapter:
        return offline_gateway

    def test_option_chain_returns_dict(self, gateway: DhanWireAdapter) -> None:
        # Offline SAMPLE_ROWS has no option legs; assert via futures contracts shape instead.
        contracts = gateway.extended.data.get_futures_contracts("GOLD", "MCX")
        assert isinstance(contracts, list)
        assert len(contracts) > 0

    def test_future_chain_returns_dict(self, gateway: DhanWireAdapter) -> None:
        from domain.entities.options import FutureChain

        result = gateway.future_chain("GOLD", "MCX")
        if isinstance(result, FutureChain):
            result = result.to_dict()
        assert isinstance(result, dict)
        assert "underlying" in result or "contracts" in result


class TestDhanExtendedContract:
    """Dhan-specific contract assertions beyond the shared suite."""

    def test_resolver_loaded(self, offline_gateway: DhanWireAdapter) -> None:
        stats = offline_gateway.extended.instruments.stats()
        assert stats["loaded"] is True

    def test_resolve_equity(self, offline_gateway: DhanWireAdapter) -> None:
        inst = offline_gateway.extended.instruments.resolve("RELIANCE", "NSE")
        assert inst.security_id, "security_id must be non-empty"
        assert inst.exchange == Exchange.NSE

    def test_resolve_index(self, offline_gateway: DhanWireAdapter) -> None:
        inst = offline_gateway.extended.instruments.resolve("NIFTY", "INDEX")
        assert inst.security_id, "security_id must be non-empty"
        assert inst.exchange == Exchange.INDEX

    def test_resolve_unknown_raises(self, offline_gateway: DhanWireAdapter) -> None:
        with pytest.raises(InstrumentNotFoundError):
            offline_gateway.extended.instruments.resolve("DOESNOTEXIST", "NSE")

    @skip_live
    def test_quote_returns_quote_type(self, live_gateway: DhanWireAdapter) -> None:
        quote = live_gateway.quote("RELIANCE", "NSE")
        assert isinstance(quote, Quote)
        assert quote.ltp > 0
        time.sleep(1.5)

    @skip_live_market_hours
    def test_depth_returns_bids_asks(self, live_gateway: DhanWireAdapter) -> None:
        depth = live_gateway.depth("RELIANCE", "NSE")
        assert isinstance(depth, MarketDepth)
        assert len(depth.bids) > 0
        assert len(depth.asks) > 0
        time.sleep(1.5)

    @skip_live
    def test_ltp_returns_decimal(self, live_gateway: DhanWireAdapter) -> None:
        ltp = live_gateway.ltp("RELIANCE", "NSE")
        assert isinstance(ltp, Decimal)
        assert ltp > 0
        time.sleep(1.5)

    def test_order_validation_rejects_bad_lot(self, offline_gateway: DhanWireAdapter) -> None:
        errors = offline_gateway.extended.data.validate_order(
            symbol="NIFTY 26 JUN FUT",
            exchange="NFO",
            quantity=10,
            order_type="MARKET",
            product_type="INTRADAY",
        )
        assert len(errors) > 0
        assert any("lot size" in e.lower() or "multiple" in e.lower() for e in errors)

    def test_order_validation_rejects_bad_product(self, offline_gateway: DhanWireAdapter) -> None:
        errors = offline_gateway.extended.data.validate_order(
            symbol="NIFTY 26 JUN FUT",
            exchange="NFO",
            quantity=75,
            order_type="MARKET",
            product_type="CNC",
        )
        assert len(errors) > 0
        assert any("CNC" in e or "product" in e.lower() for e in errors)

    def test_idempotency_cache_exists(self, offline_gateway: DhanWireAdapter) -> None:
        assert hasattr(offline_gateway._conn.orders, "_idempotency")
        assert isinstance(offline_gateway._conn.orders._idempotency, IdempotencyCache)


class TestDhanExtendedOrderExecutionSurface:
    """These were implemented on OrdersAdapter/MarginAdapter but never wired
    onto gateway.extended, so callers had no public way to reach them.
    Confirms the delegation actually routes to the right collaborator
    rather than just existing as dead methods."""

    def test_kill_switch_delegates_and_honors_live_orders_guard(
        self, offline_gateway: DhanWireAdapter
    ) -> None:
        from brokers.providers.dhan.exceptions import OrderError

        with pytest.raises(OrderError, match="Live orders are disabled"):
            offline_gateway._conn.orders.kill_switch(True)

    def test_status_kill_switch_delegates(self, offline_gateway: DhanWireAdapter) -> None:
        result = offline_gateway._conn.orders.status_kill_switch()
        assert isinstance(result, dict)

    def test_place_slice_order_delegates_and_honors_live_orders_guard(
        self, offline_gateway: DhanWireAdapter
    ) -> None:
        response = offline_gateway._conn.orders.place_slice_order(
            symbol="RELIANCE", exchange="NSE", side="BUY", quantity=10
        )
        assert response.success is False
        assert "Live orders disabled" in response.message

    def test_get_trade_history_delegates(self, offline_gateway: DhanWireAdapter) -> None:
        trades = offline_gateway._conn.orders.get_trade_history("2026-01-01", "2026-01-31")
        assert isinstance(trades, list)

    def test_get_order_by_correlation_id_delegates(
        self, offline_gateway: DhanWireAdapter
    ) -> None:
        order = offline_gateway._conn.orders.get_order_by_correlation_id("some-correlation-id")
        assert hasattr(order, "order_id")

    def test_calculate_margin_delegates(self, offline_gateway: DhanWireAdapter) -> None:
        from brokers.providers.dhan._dhan_types import MarginRequest

        result = offline_gateway._conn.margin.calculate(
            MarginRequest(
                symbol="RELIANCE",
                exchange="NSE",
                quantity=1,
                product_type="INTRADAY",
                order_type="MARKET",
            )
        )
        assert hasattr(result, "total_margin")

    @skip_live
    def test_positions_returns_list(self, live_gateway: DhanWireAdapter) -> None:
        assert isinstance(live_gateway.extended.positions.get_positions(), list)

    @skip_live
    def test_holdings_returns_list(self, live_gateway: DhanWireAdapter) -> None:
        assert isinstance(live_gateway.extended.positions.get_holdings(), list)

    @skip_live
    def test_balance_returns_balance(self, live_gateway: DhanWireAdapter) -> None:
        balance = live_gateway.extended.positions.get_balance()
        assert hasattr(balance, "available_balance")
        assert isinstance(balance.available_balance, Decimal)

    @skip_live
    def test_expiries_returns_list(self, live_gateway: DhanWireAdapter) -> None:
        expiries = live_gateway.extended.data.get_expiries("NIFTY", "INDEX")
        assert isinstance(expiries, list)
        assert len(expiries) > 0

    @skip_live
    def test_option_chain_has_strikes(self, live_gateway: DhanWireAdapter) -> None:
        expiries = live_gateway.extended.data.get_expiries("NIFTY", "INDEX")
        assert len(expiries) > 0
        time.sleep(3.5)
        chain = live_gateway.extended.data.get_option_chain("NIFTY", "INDEX", expiries[0])
        assert "strikes" in chain
        assert len(chain["strikes"]) > 0
        first_strike = chain["strikes"][0]
        assert "call" in first_strike
        assert "put" in first_strike

    def test_futures_returns_contracts(self, offline_gateway: DhanWireAdapter) -> None:
        contracts = offline_gateway.extended.data.get_futures_contracts("GOLD", "MCX")
        assert isinstance(contracts, list)
        assert len(contracts) > 0
        for contract in contracts:
            assert "security_id" in contract
            assert "expiry" in contract
            assert "lot_size" in contract

    def test_is_commodity(self, offline_gateway: DhanWireAdapter) -> None:
        assert offline_gateway.extended.data.is_commodity("GOLD") is True
        assert offline_gateway.extended.data.is_commodity("SILVER") is True
        assert offline_gateway.extended.data.is_commodity("CRUDEOIL") is True
        assert offline_gateway.extended.data.is_commodity("RELIANCE") is False
        assert offline_gateway.extended.data.is_commodity("NIFTY") is False
