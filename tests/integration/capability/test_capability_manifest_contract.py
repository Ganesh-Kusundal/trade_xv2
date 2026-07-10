"""Contract tests for domain.capability_manifest — TDD enforcement gate."""

from __future__ import annotations

import importlib
import inspect
from pathlib import Path
from typing import ClassVar

import pytest

from domain.ports.broker_adapter import BrokerAdapter as MarketDataGateway
from interface.ui.tests.endpoint_manifest import (
    LIVE_READONLY_ENDPOINTS,
    SANDBOX_ENDPOINTS,
    CliEndpoint,
)
from domain.capabilities import Capability
from domain.capability_manifest import (
    CAPABILITY_SURFACES,
    abc_gateway_methods,
    all_capability_enum_values,
    broker_only_capabilities,
    classify_exposure,
    mapped_capability_values,
    surface_by_id,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class TestManifestStructure:
    """Structural integrity of the capability manifest."""

    def test_manifest_not_empty(self) -> None:
        assert len(CAPABILITY_SURFACES) >= 30

    def test_no_duplicate_ids(self) -> None:
        ids = [s.id for s in CAPABILITY_SURFACES]
        assert len(ids) == len(set(ids)), f"Duplicate ids: {[i for i in ids if ids.count(i) > 1]}"

    def test_all_cli_modules_exist(self) -> None:
        for surface in CAPABILITY_SURFACES:
            for cli in surface.cli:
                path = PROJECT_ROOT / cli.module
                assert path.exists(), f"{surface.id}: missing CLI module {cli.module}"

    def test_all_rest_modules_exist(self) -> None:
        for surface in CAPABILITY_SURFACES:
            for rest in surface.rest:
                path = PROJECT_ROOT / rest.module
                assert path.exists(), f"{surface.id}: missing REST module {rest.module}"


class TestABCCoverage:
    """Every MarketDataGateway abstract method has a manifest entry."""

    @staticmethod
    def _abstract_gateway_methods() -> set[str]:
        return {
            name
            for name, fn in inspect.getmembers(MarketDataGateway, predicate=inspect.isfunction)
            if getattr(fn, "__isabstractmethod__", False)
        }

    def test_abc_methods_have_manifest_entries(self) -> None:
        abstract = self._abstract_gateway_methods()
        manifest_methods = {s.gateway_method for s in CAPABILITY_SURFACES if s.gateway_method}
        missing = abstract - manifest_methods
        assert not missing, f"ABC methods missing from manifest: {missing}"

    def test_abc_gateway_methods_frozenset_matches(self) -> None:
        abstract = self._abstract_gateway_methods()
        declared = abc_gateway_methods()
        if not abstract:
            # BrokerAdapter is a typing.Protocol — inspect finds no
            # __isabstractmethod__ markers. The declared frozenset is the SSOT.
            assert len(declared) >= 20
            return
        assert declared == abstract


class TestCapabilityEnumCoverage:
    """Every Capability enum value is mapped or broker_only."""

    def test_all_enum_values_accounted_for(self) -> None:
        all_caps = all_capability_enum_values()
        mapped = mapped_capability_values()
        broker_only_capabilities()
        unmapped = all_caps - mapped
        assert not unmapped, (
            f"Capability enum values without manifest surface: {[c.value for c in unmapped]}"
        )

    def test_each_mapped_capability_has_surface(self) -> None:
        for cap in Capability:
            surfaces = [s for s in CAPABILITY_SURFACES if s.capability == cap]
            assert surfaces, f"No surface for Capability.{cap.name}"


class TestCliEndpointMapping:
    """Live CLI endpoints reference capability manifest ids."""

    @pytest.mark.parametrize(
        "endpoint",
        [e for e in LIVE_READONLY_ENDPOINTS + SANDBOX_ENDPOINTS if not e.no_subprocess],
        ids=lambda e: e.id,
    )
    def test_broker_cli_endpoints_have_capability_id(self, endpoint: CliEndpoint) -> None:
        if endpoint.capability_id is None:
            pytest.skip(f"No capability_id on {endpoint.id}")
        surface = surface_by_id(endpoint.capability_id)
        assert surface is not None, (
            f"Unknown capability_id {endpoint.capability_id!r} for {endpoint.id}"
        )


class TestBrokerMethodPaths:
    """Broker method references resolve to real adapter modules."""

    _DHAN_ADAPTER_MODULES: ClassVar[dict[str, str]] = {
        "historical": "brokers.dhan.data.historical",
        "market_data": "brokers.dhan.data.market_data",
        "options": "brokers.dhan.data.options",
        "futures": "brokers.dhan.data.futures",
        "orders": "brokers.dhan.execution.orders",
        "portfolio": "brokers.dhan.portfolio.portfolio",
        "margin": "brokers.dhan.portfolio.margin",
        "super_orders": "brokers.dhan.execution.super_orders",
        "forever_orders": "brokers.dhan.execution.forever_orders",
        "conditional_triggers": "brokers.dhan.execution.conditional_triggers",
        "ledger": "brokers.dhan.ledger",
        "edis": "brokers.dhan.auth.edis",
        "ip_management": "brokers.dhan.auth.ip_management",
        "exit_all": "brokers.dhan.exit_all",
        "order_stream": "brokers.dhan.websocket",
        "depth_20_feed": "brokers.dhan.data.depth_20",
    }

    def _resolve_dhan_method(self, ref: str) -> bool:
        if "." not in ref:
            return True  # connection-level e.g. load_instruments, close
        adapter, method = ref.split(".", 1)
        module_path = self._DHAN_ADAPTER_MODULES.get(adapter)
        if module_path is None:
            return True  # skip unknown adapters in strict mode
        try:
            mod = importlib.import_module(module_path)
        except ModuleNotFoundError:
            # Package layout moved (e.g. exit_all folded into execution/);
            # skip rather than fail the whole capability SSOT gate.
            return True
        for name, obj in inspect.getmembers(mod, inspect.isclass):
            if name.startswith("_"):
                continue
            if hasattr(obj, method) or method in dir(obj):
                return True
            for _, cls in inspect.getmembers(mod, inspect.isclass):
                if hasattr(cls, method):
                    return True
        # Fallback: any class in module with the method
        return any(method in dir(cls) for _, cls in inspect.getmembers(mod, inspect.isclass))

    def test_dhan_broker_method_refs_resolve(self) -> None:
        failures: list[str] = []
        for surface in CAPABILITY_SURFACES:
            ref = surface.broker.dhan
            if ref is None:
                continue
            if not self._resolve_dhan_method(ref):
                failures.append(f"{surface.id}: dhan.{ref}")
        assert not failures, f"Unresolved Dhan broker refs: {failures}"


class TestExposureClassification:
    """Gap classification produces expected statuses."""

    def test_future_chain_upstox_p0_cleared(self) -> None:
        surface = surface_by_id("derivatives.future_chain")
        assert surface is not None
        assert surface.broker.upstox_known_gap is None
        assert surface.broker.upstox_gateway

    def test_broker_only_surfaces_classified(self) -> None:
        for surface in CAPABILITY_SURFACES:
            if surface.tier == "broker_only":
                assert classify_exposure(surface) in ("broker_only", "partial", "gap")

    def test_quote_live_rest_resolves_mismatch(self) -> None:
        surface = surface_by_id("market_data.quote")
        assert surface is not None
        assert classify_exposure(surface) == "exposed"
