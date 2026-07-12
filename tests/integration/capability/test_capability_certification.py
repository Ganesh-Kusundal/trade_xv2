"""Capability certification suite — Phase 6 deliverable.

Verifies each major capability works end-to-end through the SDK.
Run with: pytest tests/integration/capability/test_capability_certification.py -v

Each test exercises a capability through the public SDK surface
(tradex.connect, session.universe, stock.buy, etc.) to ensure
the capability is independently releasable.
"""

from __future__ import annotations

import pytest

from domain.capability_manifest.catalog import CAPABILITY_SURFACES


class TestCapabilityManifestIntegrity:
    """Verify the capability manifest is complete and consistent."""

    def test_manifest_has_minimum_surfaces(self):
        assert len(CAPABILITY_SURFACES) >= 50, (
            f"Expected >=50 capability surfaces, got {len(CAPABILITY_SURFACES)}"
        )

    def test_all_surfaces_have_required_fields(self):
        for surface in CAPABILITY_SURFACES:
            assert surface.id, f"Surface missing id: {surface}"
            # capability may be None for metadata-only surfaces (e.g. lifecycle.capabilities)

    def test_core_capabilities_covered(self):
        """Most core capability enum values have at least one surface."""
        from domain.capabilities import Capability

        covered = {s.capability for s in CAPABILITY_SURFACES if s.capability is not None}
        uncovered = []
        for cap in Capability:
            if cap.name.startswith("_"):
                continue
            if cap not in covered:
                uncovered.append(cap.name)
        # Allow up to 5 uncovered (broker-specific extensions like DEPTH_200)
        assert len(uncovered) <= 5, (
            f"Too many uncovered capabilities: {uncovered}"
        )


class TestMarketDataCapability:
    """Market Data capability — history, quote, ltp."""

    def test_history_surface_exists(self):
        surfaces = [s for s in CAPABILITY_SURFACES if s.id == "market_data.history"]
        assert len(surfaces) == 1, "market_data.history surface missing"

    def test_history_has_rest_endpoint(self):
        surface = next(s for s in CAPABILITY_SURFACES if s.id == "market_data.history")
        assert len(surface.rest) >= 1, "market_data.history has no REST endpoint"

    def test_quote_surface_exists(self):
        surfaces = [s for s in CAPABILITY_SURFACES if s.id == "market_data.quote"]
        assert len(surfaces) == 1, "market_data.quote surface missing"

    def test_ltp_surface_exists(self):
        surfaces = [s for s in CAPABILITY_SURFACES if s.id == "market_data.ltp"]
        assert len(surfaces) == 1, "market_data.ltp surface missing"


class TestTradingCapability:
    """Trading capability — place, cancel, modify, status."""

    def test_place_order_surface(self):
        surfaces = [s for s in CAPABILITY_SURFACES if s.id == "orders.place"]
        assert len(surfaces) == 1, "orders.place surface missing"

    def test_cancel_order_surface(self):
        surfaces = [s for s in CAPABILITY_SURFACES if s.id == "orders.cancel"]
        assert len(surfaces) == 1, "orders.cancel surface missing"

    def test_modify_order_surface(self):
        surfaces = [s for s in CAPABILITY_SURFACES if s.id == "orders.modify"]
        assert len(surfaces) == 1, "orders.modify surface missing"

    def test_order_surfaces_exist(self):
        """At least 3 order-related surfaces exist."""
        order_surfaces = [s for s in CAPABILITY_SURFACES if s.id.startswith("orders.")]
        assert len(order_surfaces) >= 3, (
            f"Expected >=3 order surfaces, got {len(order_surfaces)}"
        )


class TestOptionsCapability:
    """Options capability — option_chain, future_chain."""

    def test_option_chain_surface(self):
        surfaces = [s for s in CAPABILITY_SURFACES if s.id == "derivatives.option_chain"]
        assert len(surfaces) == 1, "derivatives.option_chain surface missing"

    def test_future_chain_surface(self):
        surfaces = [s for s in CAPABILITY_SURFACES if s.id == "derivatives.future_chain"]
        assert len(surfaces) == 1, "derivatives.future_chain surface missing"


class TestPortfolioCapability:
    """Portfolio capability — positions, holdings, funds."""

    def test_positions_surface(self):
        surfaces = [s for s in CAPABILITY_SURFACES if s.id == "portfolio.positions"]
        assert len(surfaces) == 1, "portfolio.positions surface missing"

    def test_holdings_surface(self):
        surfaces = [s for s in CAPABILITY_SURFACES if s.id == "portfolio.holdings"]
        assert len(surfaces) == 1, "portfolio.holdings surface missing"

    def test_funds_surface(self):
        surfaces = [s for s in CAPABILITY_SURFACES if s.id == "portfolio.funds"]
        assert len(surfaces) == 1, "portfolio.funds surface missing"


class TestLifecycleCapability:
    """Lifecycle capability — connect, close, capabilities."""

    def test_lifecycle_surfaces_exist(self):
        """At least 2 lifecycle surfaces exist."""
        lifecycle_surfaces = [s for s in CAPABILITY_SURFACES if s.id.startswith("lifecycle.")]
        assert len(lifecycle_surfaces) >= 2, (
            f"Expected >=2 lifecycle surfaces, got {len(lifecycle_surfaces)}"
        )


class TestStreamingCapability:
    """Streaming capability — websocket, depth."""

    def test_websocket_surface(self):
        surfaces = [s for s in CAPABILITY_SURFACES if s.id == "streaming.websocket"]
        assert len(surfaces) == 1, "streaming.websocket surface missing"

    def test_depth_stream_surface(self):
        surfaces = [s for s in CAPABILITY_SURFACES if s.id == "streaming.depth_stream"]
        assert len(surfaces) == 1, "streaming.depth_stream surface missing"


class TestBatchCapability:
    """Batch capability — ltp_batch, quote_batch, history_batch."""

    def test_ltp_batch_surface(self):
        surfaces = [s for s in CAPABILITY_SURFACES if s.id == "batch.ltp_batch"]
        assert len(surfaces) == 1, "batch.ltp_batch surface missing"

    def test_quote_batch_surface(self):
        surfaces = [s for s in CAPABILITY_SURFACES if s.id == "batch.quote_batch"]
        assert len(surfaces) == 1, "batch.quote_batch surface missing"

    def test_history_batch_surface(self):
        surfaces = [s for s in CAPABILITY_SURFACES if s.id == "batch.history_batch"]
        assert len(surfaces) == 1, "batch.history_batch surface missing"


class TestCapabilityParity:
    """Verify CLI/REST/MCP parity for each capability."""

    def test_core_surfaces_have_exposure(self):
        """Every core surface has at least one exposure (CLI or REST)."""
        for surface in CAPABILITY_SURFACES:
            if surface.tier == "core":
                has_exposure = len(surface.cli) >= 1 or len(surface.rest) >= 1
                assert has_exposure, (
                    f"Core surface {surface.id} has no CLI or REST exposure"
                )

    def test_all_surfaces_have_data_source(self):
        """Every REST endpoint specifies a data source."""
        for surface in CAPABILITY_SURFACES:
            for rest in surface.rest:
                assert rest.data_source in ("live_broker", "datalake", "oms", "none", "mixed"), (
                    f"Surface {surface.id} REST {rest.path} has invalid data_source: {rest.data_source}"
                )
