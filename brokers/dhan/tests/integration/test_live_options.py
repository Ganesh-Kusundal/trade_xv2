"""Live integration tests for Dhan options (expiries, option chain, greeks).

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
    gw = BrokerFactory.create(env_path=ENV_PATH, load_instruments=True)
    yield gw
    gw.close()


@pytest.mark.skipif(not _live_env_loaded, reason=".env.local with DHAN_CLIENT_ID required")
class TestLiveOptions:
    """End-to-end option chain retrieval against the live Dhan API."""

    def test_nifty_expiries(self, gateway: BrokerGateway):
        """get_expiries for NIFTY INDEX should return a non-empty list."""
        expiries = gateway.options.get_expiries("NIFTY", "INDEX")
        assert len(expiries) > 0

    def test_nifty_option_chain(self, gateway: BrokerGateway):
        """get_option_chain should return a dict with spot > 0 and strikes > 0."""
        expiries = gateway.options.get_expiries("NIFTY", "INDEX")
        assert len(expiries) > 0

        time.sleep(3.5)

        chain = gateway.options.get_option_chain("NIFTY", "INDEX", expiries[0])

        assert "spot" in chain
        assert chain["spot"] > 0

        assert "strikes" in chain
        assert len(chain["strikes"]) > 0

    def test_option_chain_has_greeks(self, gateway: BrokerGateway):
        """First strike's call dict must contain delta, theta, gamma, vega keys."""
        expiries = gateway.options.get_expiries("NIFTY", "INDEX")
        assert len(expiries) > 0

        time.sleep(3.5)

        chain = gateway.options.get_option_chain("NIFTY", "INDEX", expiries[0])
        assert len(chain["strikes"]) > 0

        first_strike = chain["strikes"][0]
        call_leg = first_strike["call"]

        assert "delta" in call_leg
        assert "theta" in call_leg
        assert "gamma" in call_leg
        assert "vega" in call_leg
