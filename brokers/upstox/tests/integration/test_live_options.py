"""Live integration tests for Upstox options.

Expiries are derived from the in-memory instrument master (the legacy
``/v2/option/expiry`` endpoint is deprecated and returns HTTP 400).
The chain still hits the live ``/v2/option/chain`` endpoint.

Skipped automatically when ``.env.upstox`` is absent, the access token is
expired, or the market is closed.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))

# ---------------------------------------------------------------------------
# Skip guard — credentials, token expiry, market hours
# ---------------------------------------------------------------------------
ENV_PATH = (
    Path(__file__).resolve().parent.parent.parent.parent.parent / ".env.upstox"
)
_live_env_loaded = False
if ENV_PATH.exists() and ENV_PATH.stat().st_size > 0:
    from dotenv import load_dotenv
    load_dotenv(ENV_PATH, override=True)
    _live_env_loaded = bool(
        os.environ.get("UPSTOX_API_KEY") and os.environ.get("UPSTOX_ACCESS_TOKEN")
    )


def _should_skip_live() -> bool:
    if not _live_env_loaded:
        return True
    if os.environ.get("UPSTOX_INTEGRATION") != "1":
        return True
    token = os.environ.get("UPSTOX_ACCESS_TOKEN", "")
    try:
        from brokers.common.auth.jwt_expiry import JwtExpiry
        exp_ms = JwtExpiry.parse_expiry_epoch_ms(token)
        if exp_ms > 0 and exp_ms < time.time() * 1000:
            return True
    except Exception:
        pass
    try:
        from tests.market_hours import is_market_open
        return not is_market_open()
    except Exception:
        # If market_hours is unavailable (e.g. not in test collection), run.
        return False


skip_live = pytest.mark.skipif(
    _should_skip_live(),
    reason="Live API tests require .env.upstox credentials, valid token, and open market hours",
)


@pytest.fixture(scope="module")
def gateway():
    from brokers.upstox.factory import UpstoxBrokerFactory
    gw = UpstoxBrokerFactory().create(env_path=ENV_PATH, load_instruments=True)
    yield gw
    gw.close()


@skip_live
class TestLiveUpstoxOptions:
    """End-to-end option chain retrieval against the live Upstox API."""

    def test_nifty_expiries(self, gateway):
        expiries = gateway._broker.options.get_expiries("NIFTY", "NFO")
        assert len(expiries) > 0
        # All expiries are valid ISO dates and at least one is in the future.
        from datetime import date
        today = date.today().isoformat()
        assert any(e >= today for e in expiries), (
            f"Expected at least one future expiry, got {expiries!r}"
        )

    def test_nifty_option_chain(self, gateway):
        expiries = gateway._broker.options.get_expiries("NIFTY", "NFO")
        assert len(expiries) > 0

        time.sleep(3.5)  # rate-limit courtesy

        chain = gateway.option_chain("NIFTY", exchange="NFO", expiry=expiries[0])
        data = chain.to_dict() if hasattr(chain, "to_dict") else chain
        assert data.get("underlying") == "NIFTY"
        assert data.get("exchange") in {"NFO", "INDEX"}
        assert data.get("expiry") == expiries[0]
        strikes = data.get("strikes", [])
        assert len(strikes) > 0, "expected at least one strike"

    def test_option_chain_has_per_leg_keys(self, gateway):
        expiries = gateway._broker.options.get_expiries("NIFTY", "NFO")
        assert len(expiries) > 0

        time.sleep(3.5)

        chain = gateway.option_chain("NIFTY", exchange="NFO", expiry=expiries[0])
        data = chain.to_dict() if hasattr(chain, "to_dict") else chain
        strikes = data.get("strikes", [])
        assert len(strikes) > 0
        first = strikes[0]
        assert isinstance(first, dict)
        assert "strike" in first
        assert "call" in first and isinstance(first["call"], dict)
        assert "put" in first and isinstance(first["put"], dict)
