"""Live integration tests for Dhan derivatives chain endpoints.

Tests option_chain() and future_chain() against the live Dhan API.

These tests require a valid .env.local with DHAN_CLIENT_ID and DHAN_ACCESS_TOKEN.
They are skipped automatically when the env file is absent.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))

from brokers.dhan.factory import BrokerFactory
from brokers.dhan.gateway import BrokerGateway

# ---------------------------------------------------------------------------
# Skip guard — only run when .env.local has valid credentials
# ---------------------------------------------------------------------------

ENV_PATH = Path(__file__).resolve().parent.parent.parent.parent.parent / ".env.local"
_live_env_loaded = False
if ENV_PATH.exists() and ENV_PATH.stat().st_size > 0:
    from dotenv import load_dotenv

    load_dotenv(ENV_PATH, override=True)
    _live_env_loaded = bool(os.environ.get("DHAN_CLIENT_ID"))


@pytest.fixture(scope="module")
def gateway() -> BrokerGateway:
    """Create a live BrokerGateway with instruments loaded."""
    gw = BrokerFactory().create(env_path=ENV_PATH, load_instruments=True)
    yield gw
    gw.close()


@pytest.mark.skipif(not _live_env_loaded, reason=".env.local with DHAN_CLIENT_ID required")
class TestLiveOptionChain:
    """Option chain endpoint tests against live Dhan API."""

    def test_option_chain_nifty(self, gateway: BrokerGateway):
        """option_chain() for NIFTY should return OptionChain with strikes."""
        chain = gateway.option_chain("NIFTY", "NFO")
        assert chain is not None
        assert hasattr(chain, "spot")
        assert chain.spot > 0
        assert hasattr(chain, "strikes")
        assert len(chain.strikes) > 0

    def test_option_chain_has_ce_pe_legs(self, gateway: BrokerGateway):
        """Option chain strikes should have CE and PE legs with greeks."""
        chain = gateway.option_chain("NIFTY", "NFO")
        if chain.strikes:
            first_strike = chain.strikes[0]
            # Verify CE leg
            assert hasattr(first_strike, "call") or first_strike.ce is not None
            # Verify PE leg
            assert hasattr(first_strike, "put") or first_strike.pe is not None

    def test_option_chain_with_explicit_expiry(self, gateway: BrokerGateway):
        """option_chain() with explicit expiry should work."""
        # Get available expiries
        expiries = gateway.extended.get_option_expiries("NIFTY", "INDEX")
        if expiries:
            time.sleep(2)
            chain = gateway.option_chain("NIFTY", "NFO", expiry=expiries[0])
            assert chain is not None
            assert chain.spot > 0
            assert len(chain.strikes) > 0

    def test_option_chain_banknifty(self, gateway: BrokerGateway):
        """option_chain() for BANKNIFTY should return valid chain."""
        chain = gateway.option_chain("BANKNIFTY", "NFO")
        assert chain is not None
        assert chain.spot > 0
        assert len(chain.strikes) > 0
        time.sleep(2)


@pytest.mark.skipif(not _live_env_loaded, reason=".env.local with DHAN_CLIENT_ID required")
class TestLiveFutureChain:
    """Futures chain endpoint tests against live Dhan API."""

    def test_future_chain_nifty(self, gateway: BrokerGateway):
        """future_chain() for NIFTY should return FutureChain with contracts."""
        chain = gateway.future_chain("NIFTY", "NFO")
        assert chain is not None
        assert hasattr(chain, "underlying")
        assert chain.underlying.upper() == "NIFTY"
        assert hasattr(chain, "expiries")
        assert len(chain.expiries) > 0
        assert hasattr(chain, "contracts")
        assert len(chain.contracts) > 0

    def test_future_chain_contract_schema(self, gateway: BrokerGateway):
        """Future contracts should have symbol, expiry, lot_size."""
        chain = gateway.future_chain("NIFTY", "NFO")
        if chain.contracts:
            contract = chain.contracts[0]
            assert hasattr(contract, "symbol")
            assert hasattr(contract, "expiry")
            assert hasattr(contract, "lot_size")

    def test_future_chain_banknifty(self, gateway: BrokerGateway):
        """future_chain() for BANKNIFTY should return valid chain."""
        chain = gateway.future_chain("BANKNIFTY", "NFO")
        assert chain is not None
        assert chain.underlying.upper() == "BANKNIFTY"
        assert len(chain.expiries) > 0
        assert len(chain.contracts) > 0
        time.sleep(2)

    def test_future_chain_multiple_expiries(self, gateway: BrokerGateway):
        """future_chain() should return multiple expiry dates."""
        chain = gateway.future_chain("NIFTY", "NFO")
        # Index futures typically have near, mid, far month contracts
        assert len(chain.expiries) >= 2, f"Expected ≥2 expiries, got {len(chain.expiries)}"
