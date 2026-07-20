"""MarketCoverageContract — guarantees every declared MarketCoverage has coverage.

Driven entirely by ``BrokerCapabilities.market_surfaces`` (the single source of
truth for asset/exchange coverage). This is the mechanism that makes adding a
broker or exchange a *data* edit: the offline structural tests validate every
declared lane, and the live walk asserts behavior for every (surface, operation)
without any ``if broker == "dhan"`` branch in this shared code.

Subclass in each broker's contract directory and provide:
  * ``capabilities`` fixture — returns the broker's ``BrokerCapabilities``
    (offline; typically the capability factory result).
  * ``live_gateway`` fixture — returns a credentialed gateway, or skips.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from domain import Quote
from domain.capabilities.market_surface import OPERATIONS, MarketCoverage
from domain.instruments.instrument_id import allowed_exchanges

# Operations that have a live gateway call to assert against.
_LIVE_OPS = frozenset({"quote", "ltp", "option_chain", "future_chain"})


class MarketCoverageContract:
    """Shared market-coverage contract.

    Subclasses must provide a module-level ``capabilities`` fixture (returns the
    broker's ``BrokerCapabilities``) and a ``live_gateway`` fixture (returns a
    credentialed gateway, or skips).
    """

    # ── Offline: structural validity of every declared surface ────────────

    def test_every_declared_surface_is_served(self, capabilities) -> None:
        surfaces = capabilities.market_surfaces
        assert surfaces, "broker declares no market_surfaces"
        for s in surfaces:
            assert capabilities.serves(s.asset_kind, s.exchange), (
                f"declared surface not served by serves(): {s}"
            )

    def test_surface_operations_are_valid(self, capabilities) -> None:
        for s in capabilities.market_surfaces:
            invalid = s.operations - OPERATIONS
            assert not invalid, f"surface {s} declares unknown operations: {invalid}"

    def test_surface_exchange_is_allowed(self, capabilities) -> None:
        allowed = allowed_exchanges()
        for s in capabilities.market_surfaces:
            assert s.exchange in allowed, (
                f"surface exchange {s.exchange!r} not in allowed_exchanges()"
            )

    def test_surface_probe_symbol_present(self, capabilities) -> None:
        for s in capabilities.market_surfaces:
            assert s.probe_symbol, f"surface {s} is missing a probe_symbol"

    def test_mcx_futures_covered_for_both_brokers(self, capabilities) -> None:
        # Cross-broker parity lane required by the asset-coverage audit.
        from domain.instruments.asset_kind import AssetKind

        assert capabilities.serves(AssetKind.FUTURES, "MCX"), "MCX futures lane must be declared"

    # ── Live: behavioral assertion for every (surface, operation) lane ────

    @pytest.mark.live_readonly
    def test_live_coverage_walks_every_lane(self, live_gateway) -> None:
        caps = live_gateway.capabilities()
        for s in caps.market_surfaces:
            for op in s.operations & _LIVE_OPS:
                self._assert_live_op(live_gateway, s, op)

    @staticmethod
    def _assert_live_op(gw, s: MarketCoverage, op: str) -> None:
        if op == "quote":
            q = gw.quote(s.probe_symbol, s.exchange)
            assert isinstance(q, Quote), f"quote() must return Quote for {s}"
            assert q.ltp is not None and q.ltp >= 0, f"quote ltp invalid for {s}"
        elif op == "ltp":
            p = gw.ltp(s.probe_symbol, s.exchange)
            assert isinstance(p, Decimal) and p >= 0, f"ltp invalid for {s}"
        elif op == "option_chain":
            r = gw.option_chain(s.probe_symbol, s.exchange)
            assert r is not None, f"option_chain() returned None for {s}"
        elif op == "future_chain":
            r = gw.future_chain(s.probe_symbol, s.exchange)
            assert r is not None, f"future_chain() returned None for {s}"


__all__ = ["MarketCoverageContract"]
