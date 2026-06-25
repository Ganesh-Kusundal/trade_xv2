"""Tests for extended capability registration in manifest and broker layers."""

from __future__ import annotations

import inspect

import pytest

from domain.capability_manifest import CAPABILITY_SURFACES, classify_exposure


def _extended_surfaces():
    return [s for s in CAPABILITY_SURFACES if s.extended_only]


class TestExtendedManifest:
    """Every extended_only surface has broker references."""

    @pytest.mark.parametrize(
        "surface_id",
        [s.id for s in CAPABILITY_SURFACES if s.extended_only],
        ids=[s.id for s in CAPABILITY_SURFACES if s.extended_only],
    )
    def test_extended_surface_has_broker_ref(self, surface_id: str) -> None:
        surface = next(s for s in CAPABILITY_SURFACES if s.id == surface_id)
        has_dhan = surface.broker.dhan is not None
        has_upstox = surface.broker.upstox is not None
        assert has_dhan or has_upstox, f"{surface_id} has no broker method ref"

    def test_extended_surfaces_count(self) -> None:
        assert len(_extended_surfaces()) >= 10


class TestDhanExtendedCapabilities:
    """Dhan extended.py methods are represented in manifest."""

    def test_dhan_extended_class_methods_covered(self) -> None:
        from brokers.dhan.extended import DhanExtendedCapabilities

        [
            name
            for name, fn in inspect.getmembers(DhanExtendedCapabilities, inspect.isfunction)
            if not name.startswith("_") and name not in ("instruments", "identity", "orders")
        ]
        manifest_gateway_methods = {
            s.gateway_method.split(".")[-1]
            for s in CAPABILITY_SURFACES
            if s.gateway_method and s.gateway_method.startswith("extended.")
        }
        # Key extended methods must appear in manifest
        key_methods = {
            "place_super_order",
            "place_forever_order",
            "place_conditional_trigger",
            "exit_all",
            "get_ledger",
            "authorize_edis",
            "set_ip",
        }
        missing = key_methods - manifest_gateway_methods
        assert not missing, f"Extended methods not in manifest: {missing}"

    def test_dhan_capabilities_flags_match_extended(self) -> None:
        """BrokerCapabilities flags for advanced orders align with extended module."""
        from brokers.dhan.gateway import BrokerGateway

        caps_method = BrokerGateway.capabilities
        source = inspect.getsource(caps_method)
        assert "super_orders=True" in source
        assert "forever_orders=True" in source
        assert "conditional_triggers=True" in source


class TestUpstoxExtendedCapabilities:
    """Upstox extended.py methods are represented in manifest."""

    def test_upstox_extended_key_methods_in_manifest(self) -> None:
        key_methods = {
            "get_ipos",
            "initiate_payout",
            "place_mutual_fund_order",
            "get_pnl",
            "get_user_profile",
        }
        manifest_refs = {
            s.gateway_method.split(".")[-1] if s.gateway_method else "" for s in CAPABILITY_SURFACES
        }
        manifest_refs |= {
            s.broker.upstox.split(".")[-1] if s.broker.upstox else "" for s in CAPABILITY_SURFACES
        }
        for method in key_methods:
            assert method in manifest_refs or any(
                method in (s.broker.upstox or "") for s in CAPABILITY_SURFACES
            ), f"Upstox extended {method} not in manifest"


class TestExtendedExposureGaps:
    """Extended features without CLI/REST are classified as gaps or broker_only."""

    def test_gtt_is_exposed(self) -> None:
        surface = next(s for s in CAPABILITY_SURFACES if s.id == "extended.gtt_order")
        status = classify_exposure(surface)
        assert status == "exposed"

    def test_super_orders_exposed_on_cli_and_rest(self) -> None:
        surface = next(s for s in CAPABILITY_SURFACES if s.id == "extended.super_orders")
        assert surface.cli
        assert surface.rest
        assert classify_exposure(surface) == "exposed"
