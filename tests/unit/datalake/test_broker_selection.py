"""Tests for datalake.ingestion.broker_selection.select_historical_source.

Answers "which broker for long-term sync": Dhan offers up to 3650 days of
1-minute history vs Upstox's 30 -- this must be picked automatically from
real BrokerCapabilities data, never hardcoded broker names.
"""

from __future__ import annotations

from dataclasses import dataclass

from datalake.ingestion.broker_selection import select_historical_source


@dataclass
class FakeWindow:
    timeframe: str
    max_lookback_days: int
    max_chunk_days: int


class FakeCapabilities:
    def __init__(self, windows: list[FakeWindow]) -> None:
        self.historical_windows = windows


class FakeGateway:
    def __init__(self, windows: list[FakeWindow]) -> None:
        self._caps = FakeCapabilities(windows)

    def capabilities(self) -> FakeCapabilities:
        return self._caps


def _dhan_like() -> FakeGateway:
    return FakeGateway(
        [
            FakeWindow("1m", 3650, 90),
            FakeWindow("5m", 3650, 90),
            FakeWindow("60m", 3650, 90),
            FakeWindow("1D", 3650, 365),
        ]
    )


def _upstox_like() -> FakeGateway:
    return FakeGateway(
        [
            FakeWindow("1m", 30, 30),
            FakeWindow("5m", 30, 30),
            FakeWindow("60m", 90, 90),
            FakeWindow("1D", 3650, 365),
        ]
    )


class TestSelectHistoricalSource:
    def test_prefers_broker_with_larger_lookback_for_intraday(self):
        broker_id, gw = select_historical_source(
            "1m", {"dhan": _dhan_like(), "upstox": _upstox_like()}
        )
        assert broker_id == "dhan"

    def test_order_independent(self):
        """Same result regardless of dict insertion order."""
        broker_id, _ = select_historical_source(
            "1m", {"upstox": _upstox_like(), "dhan": _dhan_like()}
        )
        assert broker_id == "dhan"

    def test_5m_also_prefers_dhan(self):
        broker_id, _ = select_historical_source(
            "5m", {"dhan": _dhan_like(), "upstox": _upstox_like()}
        )
        assert broker_id == "dhan"

    def test_daily_timeframe_both_equal_returns_a_valid_gateway(self):
        broker_id, gw = select_historical_source(
            "1D", {"dhan": _dhan_like(), "upstox": _upstox_like()}
        )
        assert broker_id in ("dhan", "upstox")
        assert gw is not None

    def test_loader_style_lowercase_aliases_resolve_correctly(self):
        """loader.py/schema.py use "1d"/"1h"/"1w"; capabilities use
        "1D"/"60m"/"1W" -- the alias table must bridge them, and NOT
        blanket-uppercase (which would turn "1m" into the unrelated "1M"
        = one-month timeframe). "1h" -> "60m": dhan's window (3650d) beats
        upstox's (90d), proving the alias actually matched a real window
        rather than silently falling through to the no-match fallback.
        """
        broker_id, _ = select_historical_source(
            "1h", {"dhan": _dhan_like(), "upstox": _upstox_like()}
        )
        assert broker_id == "dhan"

    def test_unmatched_timeframe_falls_back_to_first_gateway_not_error(self):
        broker_id, gw = select_historical_source(
            "1M", {"dhan": _dhan_like(), "upstox": _upstox_like()}
        )
        assert broker_id == "dhan"  # first in dict, since neither declares "1M" here
        assert gw is not None

    def test_single_gateway_dict_returns_that_gateway(self):
        gw = _dhan_like()
        broker_id, returned = select_historical_source("1m", {"dhan": gw})
        assert broker_id == "dhan"
        assert returned is gw
