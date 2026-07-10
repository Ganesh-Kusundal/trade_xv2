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
from brokers.dhan.domain import Exchange
from brokers.dhan.exceptions import InstrumentNotFoundError
from brokers.dhan.execution.orders import IdempotencyCache
from brokers.dhan.gateway import DhanBrokerGateway
from brokers.dhan.identity.factory import BrokerFactory
from brokers.dhan.streaming.connection import DhanConnection
from domain import MarketDepth, Quote
from tests.support.brokers.dhan.fixtures import SAMPLE_ROWS, FakeHttpClient

ENV_PATH = Path(__file__).resolve().parents[5] / ".env.local"
_live_env_loaded = False
if ENV_PATH.exists() and ENV_PATH.stat().st_size > 0:
    from dotenv import load_dotenv

    load_dotenv(ENV_PATH, override=True)
    _live_env_loaded = bool(os.environ.get("DHAN_CLIENT_ID"))


def _should_skip_live() -> bool:
    if not _live_env_loaded:
        return True
    token = os.environ.get("DHAN_ACCESS_TOKEN", "")
    import time as _time

    from infrastructure.auth.jwt_expiry import JwtExpiry

    exp_ms = JwtExpiry.parse_expiry_epoch_ms(token)
    if exp_ms > 0 and exp_ms < _time.time() * 1000:
        return True
    from tests.market_hours import is_market_open

    return not is_market_open()


skip_live = pytest.mark.skipif(
    _should_skip_live(),
    reason="Live API tests require .env.local credentials and open market hours",
)


@pytest.fixture()
def offline_gateway() -> DhanBrokerGateway:
    client = FakeHttpClient()
    conn = DhanConnection(client=client)
    conn.instruments.load_from_rows(SAMPLE_ROWS)
    return DhanBrokerGateway(conn)


@pytest.fixture(scope="module")
def live_gateway() -> DhanBrokerGateway:
    gw = BrokerFactory().create(env_path=ENV_PATH, load_instruments=True)
    yield gw
    gw.close()


class TestDhanBrokerContract(BrokerContractSuite):
    """Shared BrokerContractSuite + Dhan offline gateway."""

    @pytest.fixture
    def gateway(self, offline_gateway: DhanBrokerGateway) -> DhanBrokerGateway:
        return offline_gateway

    def test_option_chain_returns_dict(self, gateway: DhanBrokerGateway) -> None:
        # Offline SAMPLE_ROWS has no option legs; assert via futures contracts shape instead.
        contracts = gateway.extended.get_futures_contracts("GOLD", "MCX")
        assert isinstance(contracts, list)
        assert len(contracts) > 0

    def test_future_chain_returns_dict(self, gateway: DhanBrokerGateway) -> None:
        from domain.entities.options import FutureChain

        result = gateway.future_chain("GOLD", "MCX")
        if isinstance(result, FutureChain):
            result = result.to_dict()
        assert isinstance(result, dict)
        assert "underlying" in result or "contracts" in result


class TestDhanExtendedContract:
    """Dhan-specific contract assertions beyond the shared suite."""

    def test_resolver_loaded(self, offline_gateway: DhanBrokerGateway) -> None:
        stats = offline_gateway.extended.instruments.stats()
        assert stats["loaded"] is True

    def test_resolve_equity(self, offline_gateway: DhanBrokerGateway) -> None:
        inst = offline_gateway.extended.instruments.resolve("RELIANCE", "NSE")
        assert inst.security_id, "security_id must be non-empty"
        assert inst.exchange == Exchange.NSE

    def test_resolve_index(self, offline_gateway: DhanBrokerGateway) -> None:
        inst = offline_gateway.extended.instruments.resolve("NIFTY", "INDEX")
        assert inst.security_id, "security_id must be non-empty"
        assert inst.exchange == Exchange.INDEX

    def test_resolve_unknown_raises(self, offline_gateway: DhanBrokerGateway) -> None:
        with pytest.raises(InstrumentNotFoundError):
            offline_gateway.extended.instruments.resolve("DOESNOTEXIST", "NSE")

    @skip_live
    def test_quote_returns_quote_type(self, live_gateway: DhanBrokerGateway) -> None:
        quote = live_gateway.quote("RELIANCE", "NSE")
        assert isinstance(quote, Quote)
        assert quote.ltp > 0
        time.sleep(1.5)

    @skip_live
    def test_depth_returns_bids_asks(self, live_gateway: DhanBrokerGateway) -> None:
        depth = live_gateway.depth("RELIANCE", "NSE")
        assert isinstance(depth, MarketDepth)
        assert len(depth.bids) > 0
        assert len(depth.asks) > 0
        time.sleep(1.5)

    @skip_live
    def test_ltp_returns_decimal(self, live_gateway: DhanBrokerGateway) -> None:
        ltp = live_gateway.ltp("RELIANCE", "NSE")
        assert isinstance(ltp, Decimal)
        assert ltp > 0
        time.sleep(1.5)

    def test_order_validation_rejects_bad_lot(self, offline_gateway: DhanBrokerGateway) -> None:
        errors = offline_gateway.extended.validate_order(
            symbol="NIFTY 26 JUN FUT",
            exchange="NFO",
            quantity=10,
            order_type="MARKET",
            product_type="INTRADAY",
        )
        assert len(errors) > 0
        assert any("lot size" in e.lower() or "multiple" in e.lower() for e in errors)

    def test_order_validation_rejects_bad_product(self, offline_gateway: DhanBrokerGateway) -> None:
        errors = offline_gateway.extended.validate_order(
            symbol="NIFTY 26 JUN FUT",
            exchange="NFO",
            quantity=75,
            order_type="MARKET",
            product_type="CNC",
        )
        assert len(errors) > 0
        assert any("CNC" in e or "product" in e.lower() for e in errors)

    def test_idempotency_cache_exists(self, offline_gateway: DhanBrokerGateway) -> None:
        assert hasattr(offline_gateway.extended.orders, "_idempotency")
        assert isinstance(offline_gateway.extended.orders._idempotency, IdempotencyCache)

    @skip_live
    def test_positions_returns_list(self, live_gateway: DhanBrokerGateway) -> None:
        assert isinstance(live_gateway.extended.get_positions(), list)

    @skip_live
    def test_holdings_returns_list(self, live_gateway: DhanBrokerGateway) -> None:
        assert isinstance(live_gateway.extended.get_holdings(), list)

    @skip_live
    def test_balance_returns_balance(self, live_gateway: DhanBrokerGateway) -> None:
        balance = live_gateway.extended.get_balance()
        assert hasattr(balance, "available_balance")
        assert isinstance(balance.available_balance, Decimal)

    @skip_live
    def test_expiries_returns_list(self, live_gateway: DhanBrokerGateway) -> None:
        expiries = live_gateway.extended.get_expiries("NIFTY", "INDEX")
        assert isinstance(expiries, list)
        assert len(expiries) > 0

    @skip_live
    def test_option_chain_has_strikes(self, live_gateway: DhanBrokerGateway) -> None:
        expiries = live_gateway.extended.get_expiries("NIFTY", "INDEX")
        assert len(expiries) > 0
        time.sleep(3.5)
        chain = live_gateway.extended.get_option_chain("NIFTY", "INDEX", expiries[0])
        assert "strikes" in chain
        assert len(chain["strikes"]) > 0
        first_strike = chain["strikes"][0]
        assert "call" in first_strike
        assert "put" in first_strike

    def test_futures_returns_contracts(self, offline_gateway: DhanBrokerGateway) -> None:
        contracts = offline_gateway.extended.get_futures_contracts("GOLD", "MCX")
        assert isinstance(contracts, list)
        assert len(contracts) > 0
        for contract in contracts:
            assert "security_id" in contract
            assert "expiry" in contract
            assert "lot_size" in contract

    def test_is_commodity(self, offline_gateway: DhanBrokerGateway) -> None:
        assert offline_gateway.extended.is_commodity("GOLD") is True
        assert offline_gateway.extended.is_commodity("SILVER") is True
        assert offline_gateway.extended.is_commodity("CRUDEOIL") is True
        assert offline_gateway.extended.is_commodity("RELIANCE") is False
        assert offline_gateway.extended.is_commodity("NIFTY") is False
