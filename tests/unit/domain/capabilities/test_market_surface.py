"""Unit tests for MarketCoverage + BrokerCapabilities.market_surfaces / serves()."""

from __future__ import annotations

from brokers.dhan.config.capabilities import dhan_capabilities
from brokers.upstox.capabilities.snapshot import upstox_capabilities
from domain.capabilities.market_surface import (
    LTP,
    OPTION_CHAIN,
    QUOTE,
    MarketCoverage,
)
from domain.instruments.asset_kind import AssetKind


def _dhan() -> set[tuple[str, str]]:
    return {(s.asset_kind.value, s.exchange) for s in dhan_capabilities().market_surfaces}


def _upstox() -> set[tuple[str, str]]:
    return {(s.asset_kind.value, s.exchange) for s in upstox_capabilities().market_surfaces}


class TestMarketCoverage:
    def test_frozen_and_equality(self):
        a = MarketCoverage(AssetKind.EQUITY, "NSE", "RELIANCE", frozenset({QUOTE, LTP}))
        b = MarketCoverage(AssetKind.EQUITY, "NSE", "RELIANCE", frozenset({LTP, QUOTE}))
        assert a == b
        assert hash(a) == hash(b)
        assert a.supports_operation(QUOTE)
        assert not a.supports_operation(OPTION_CHAIN)

    def test_serves_by_enum_and_string(self):
        caps = dhan_capabilities()
        assert caps.serves(AssetKind.EQUITY, "NSE")
        assert caps.serves("equity", "NSE")  # lenient string parse
        assert not caps.serves("equity", "BSE")
        assert not caps.serves("CRYPTO", "NSE")  # unknown asset kind -> False
        assert not caps.serves("not-a-kind", "NSE")


class TestDhanSurfaces:
    def test_core_lanes_present(self):
        lanes = _dhan()
        assert ("EQUITY", "NSE") in lanes
        assert ("INDEX", "NSE") in lanes
        assert ("OPTIONS", "NFO") in lanes
        assert ("FUTURES", "NFO") in lanes

    def test_mcx_futures_and_options_and_cds_spot(self):
        lanes = _dhan()
        assert ("FUTURES", "MCX") in lanes
        assert ("OPTIONS", "MCX") in lanes  # Dhan supports MCX options
        assert ("SPOT", "CDS") in lanes

    def test_probe_symbols(self):
        caps = dhan_capabilities()
        eq = next(s for s in caps.market_surfaces if s.asset_kind == AssetKind.EQUITY)
        assert eq.probe_symbol == "RELIANCE"
        mcx = next(s for s in caps.market_surfaces if s.exchange == "MCX")
        assert mcx.probe_symbol == "GOLD"
        cds = next(s for s in caps.market_surfaces if s.exchange == "CDS")
        assert cds.probe_symbol == "USDINR"


class TestUpstoxSurfaces:
    def test_core_lanes_present(self):
        lanes = _upstox()
        assert ("EQUITY", "NSE") in lanes
        assert ("INDEX", "NSE") in lanes
        assert ("OPTIONS", "NFO") in lanes
        assert ("FUTURES", "NFO") in lanes

    def test_mcx_futures_and_cds_spot(self):
        lanes = _upstox()
        assert ("FUTURES", "MCX") in lanes
        assert ("SPOT", "CDS") in lanes

    def test_mcx_options_not_claimed_without_api_confirmation(self):
        # Upstox MCX options support is pending confirmation; do not over-claim.
        assert ("OPTIONS", "MCX") not in _upstox()
