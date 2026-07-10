"""Regression tests for UpstoxBrokerGateway history() and capability self-check.

TASK B: history() must surface fetch failures instead of silently returning an
empty DataFrame (so callers can distinguish "no data" from "fetch failed").

TASK C: UpstoxBrokerGateway.__init__ must run validate_gateway_capabilities(self)
for symmetry with DhanBrokerGateway.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from brokers.common.capabilities_validator import (
    enforce_gateway_capabilities,
    validate_gateway_capabilities,
)
from brokers.upstox.gateway import UpstoxBrokerGateway


# ── TASK B: history() surfaces errors ──


def _gateway_with_failing_fetch(exc: BaseException) -> UpstoxBrokerGateway:
    """Build a gateway whose underlying candle fetch raises ``exc``."""
    broker = MagicMock()
    broker.instrument_resolver.resolve.return_value = MagicMock(
        instrument_key="NSE_EQ|INE002A01018"
    )
    gw = UpstoxBrokerGateway(broker)
    gw._historical.fetch_candles = MagicMock(side_effect=exc)
    return gw


def test_history_raises_when_fetch_raises() -> None:
    gw = _gateway_with_failing_fetch(RuntimeError("boom"))
    with pytest.raises(RuntimeError):
        gw.history("RELIANCE", "NSE", timeframe="1D", lookback_days=5)


def test_history_raises_upstox_api_error() -> None:
    from brokers.upstox.auth.exceptions import UpstoxApiError

    gw = _gateway_with_failing_fetch(UpstoxApiError("rate limited", status_code=429))
    with pytest.raises(UpstoxApiError):
        gw.history("RELIANCE", "NSE", timeframe="1D", lookback_days=5)


def test_history_does_not_return_empty_on_failure() -> None:
    gw = _gateway_with_failing_fetch(ValueError("bad"))
    result = "UNSET"
    try:
        result = gw.history("RELIANCE", "NSE", timeframe="1D", lookback_days=5)
    except Exception:
        result = "RAISED"
    assert result == "RAISED"


def test_history_success_path_unaffected() -> None:
    broker = MagicMock()
    broker.instrument_resolver.resolve.return_value = MagicMock(
        instrument_key="NSE_EQ|INE002A01018"
    )
    gw = UpstoxBrokerGateway(broker)
    df = pd.DataFrame({"close": [1, 2, 3]})
    gw._historical.fetch_candles = MagicMock(return_value=df)
    out = gw.history("RELIANCE", "NSE", timeframe="1D", lookback_days=5)
    assert out is df


# ── TASK C: capability self-check ──


def test_gateway_construct_runs_capability_check() -> None:
    broker = MagicMock()
    with patch(
        "brokers.upstox.gateway.enforce_gateway_capabilities",
        wraps=enforce_gateway_capabilities,
    ) as spy:
        gw = UpstoxBrokerGateway(broker)
        assert isinstance(gw, UpstoxBrokerGateway)
        spy.assert_called_once_with(gw)


def test_validate_gateway_capabilities_flags_missing_method(caplog) -> None:
    """A fake gateway advertising supports_modify_order but lacking the method
    must log a WARNING and be reported as a mismatch."""

    class _Caps:
        supports_modify_order = True

    class _FakeGateway:
        def capabilities(self) -> _Caps:
            return _Caps()

        # NOTE: deliberately no modify_order method

    import logging

    with caplog.at_level(logging.WARNING):
        mismatches = validate_gateway_capabilities(_FakeGateway())

    assert len(mismatches) == 1
    assert any("supports_modify_order" in m for m in mismatches)
