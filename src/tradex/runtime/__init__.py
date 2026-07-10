"""Collapsed ``tradex.runtime`` facade.

All former shim modules are provided via a meta path finder that re-exports
the canonical implementation and emits :class:`DeprecationWarning`.

Do not add new code here. Import from domain / application / infrastructure /
runtime instead.
"""

from __future__ import annotations

import importlib
import importlib.abc
import importlib.machinery
import sys
import types
from typing import Any

from tradex.runtime._deprecation import warn_facade

# Fully-qualified facade module -> fully-qualified canonical module
FACADE_TO_CANONICAL: dict[str, str] = {
    'tradex.runtime.adapter_factory': 'infrastructure.adapter_factory',
    'tradex.runtime.adapters': 'infrastructure.adapters',
    'tradex.runtime.adapters.extensions': 'infrastructure.adapters.extensions',
    'tradex.runtime.adapters.historical_mapper': 'infrastructure.adapters.historical_mapper',
    'tradex.runtime.adapters.market_data_gateway_adapter': 'infrastructure.adapters.market_data_gateway_adapter',
    'tradex.runtime.async_compat': 'infrastructure.async_compat',
    'tradex.runtime.auth': 'infrastructure.auth',
    'tradex.runtime.auth.credential_resolver': 'infrastructure.auth.credential_resolver',
    'tradex.runtime.auth.credential_validator': 'infrastructure.auth.credential_validator',
    'tradex.runtime.auth.env_token': 'infrastructure.auth.env_token',
    'tradex.runtime.auth.environment_bootstrap': 'infrastructure.auth.environment_bootstrap',
    'tradex.runtime.auth.jwt_expiry': 'infrastructure.auth.jwt_expiry',
    'tradex.runtime.auth.metrics': 'infrastructure.auth.metrics',
    'tradex.runtime.auth.registry': 'infrastructure.auth.registry',
    'tradex.runtime.auth.token': 'infrastructure.auth.token',
    'tradex.runtime.auth.token_ensure': 'infrastructure.auth.token_ensure',
    'tradex.runtime.auth.token_persistence': 'infrastructure.auth.token_persistence',
    'tradex.runtime.auth.token_policy': 'infrastructure.auth.token_policy',
    'tradex.runtime.auth.totp_cooldown': 'infrastructure.auth.totp_cooldown',
    'tradex.runtime.batch_executor': 'infrastructure.batch_executor',
    'tradex.runtime.batch_mixin': 'infrastructure.batch_mixin',
    'tradex.runtime.bootstrap': 'infrastructure.bootstrap',
    'tradex.runtime.broker_plugin': 'infrastructure.broker_plugin',
    'tradex.runtime.broker_port': 'domain.ports.broker_gateway',
    'tradex.runtime.build_info': 'infrastructure.build_info',
    'tradex.runtime.candle_aggregator': 'application.streaming.candle_aggregator',
    'tradex.runtime.capabilities': 'domain.capabilities.broker_capabilities',
    'tradex.runtime.clock': 'infrastructure.time.clock',
    'tradex.runtime.common_broker_access': 'infrastructure.common_broker_access',
    'tradex.runtime.connection': 'infrastructure.connection',
    'tradex.runtime.connection.authenticated_readiness': 'infrastructure.connection.authenticated_readiness',
    'tradex.runtime.connection.bootstrap_result': 'infrastructure.connection.bootstrap_result',
    'tradex.runtime.connection.errors': 'infrastructure.connection.errors',
    'tradex.runtime.connection_pool': 'infrastructure.pool.connection_pool',
    'tradex.runtime.dtos': 'domain.models.dtos',
    'tradex.runtime.env_loader': 'infrastructure.config.env_loader',
    'tradex.runtime.errors': 'domain.errors',
    'tradex.runtime.extensions': 'domain.extensions.broker_bundle',
    'tradex.runtime.extensions.forever_order': 'domain.extensions.forever_order',
    'tradex.runtime.extensions.fundamentals': 'domain.extensions.fundamentals',
    'tradex.runtime.extensions.native_slice_order': 'domain.extensions.native_slice_order',
    'tradex.runtime.extensions.news': 'domain.extensions.news',
    'tradex.runtime.extensions.registry': 'domain.extensions.broker_bundle',
    'tradex.runtime.extensions.super_order': 'domain.extensions.super_order',
    'tradex.runtime.factory': 'infrastructure.gateway.provider_factory',
    'tradex.runtime.gateway': 'infrastructure.gateway.base',
    'tradex.runtime.gateway_errors': 'domain.errors',
    'tradex.runtime.gateway_execution': 'infrastructure.gateway.execution',
    'tradex.runtime.gateway_factory': 'infrastructure.gateway.factory',
    'tradex.runtime.historical_coordinator': 'application.data.historical_coordinator',
    'tradex.runtime.infrastructure': 'runtime.broker_infrastructure',
    'tradex.runtime.instruments': 'infrastructure.instruments',
    'tradex.runtime.mappers': 'infrastructure.mappers',
    'tradex.runtime.mappers.order_mapper': 'infrastructure.mappers.order_mapper',
    'tradex.runtime.models': 'domain.models.routing',
    'tradex.runtime.observability': 'infrastructure.observability',
    'tradex.runtime.observability.audit': 'infrastructure.observability.audit',
    'tradex.runtime.observability.health_check': 'infrastructure.observability.health_check',
    'tradex.runtime.observability.http_server': 'infrastructure.observability.http_server',
    'tradex.runtime.options': 'domain.options',
    'tradex.runtime.options.chain_normalizer': 'domain.options.chain_normalizer',
    'tradex.runtime.options.gateway_facade': 'domain.options.gateway_facade',
    'tradex.runtime.policy': 'domain.policies.source_selection',
    'tradex.runtime.policy_defaults': 'domain.policies.defaults',
    'tradex.runtime.provenance': 'application.data.provenance',
    'tradex.runtime.quota_decorator': 'application.scheduling.quota_decorator',
    'tradex.runtime.quota_scheduler': 'application.scheduling.quota_scheduler',
    'tradex.runtime.reconciliation': 'application.oms.reconciliation',
    'tradex.runtime.reconciliation.engine': 'application.oms.reconciliation.engine',
    'tradex.runtime.registry': 'application.composer.registry',
    'tradex.runtime.resilience': 'infrastructure.resilience',
    'tradex.runtime.resilience.backoff': 'infrastructure.resilience.backoff',
    'tradex.runtime.resilience.broker_health_monitor': 'infrastructure.resilience.broker_health_monitor',
    'tradex.runtime.resilience.circuit_breaker': 'infrastructure.resilience.circuit_breaker',
    'tradex.runtime.resilience.error_codes': 'infrastructure.resilience.error_codes',
    'tradex.runtime.resilience.errors': 'infrastructure.resilience.errors',
    'tradex.runtime.resilience.rate_limiter': 'infrastructure.resilience.rate_limiter',
    'tradex.runtime.resilience.retry': 'infrastructure.resilience.retry',
    'tradex.runtime.router': 'application.composer.router',
    'tradex.runtime.services': 'application.services',
    'tradex.runtime.services.data_validator': 'application.services.data_validator',
    'tradex.runtime.services.download_engine': 'application.services.download_engine',
    'tradex.runtime.services.historical_data': 'application.services.historical_data',
    'tradex.runtime.services.instrument_registry': 'application.services.instrument_registry',
    'tradex.runtime.services.production_readiness': 'application.services.production_readiness',
    'tradex.runtime.session_infra': 'runtime.session_infra',
    'tradex.runtime.settings': 'infrastructure.config.settings',
    'tradex.runtime.ssl_hardening': 'infrastructure.security.ssl_hardening',
    'tradex.runtime.stream_orchestrator': 'application.streaming.orchestrator',
    'tradex.runtime.submission_pipeline': 'application.execution.submission_pipeline'
}


def _has_facade_children(fullname: str) -> bool:
    prefix = fullname + "."
    return any(key.startswith(prefix) for key in FACADE_TO_CANONICAL)


class _FacadeLoader(importlib.abc.Loader):
    """Load a facade module by re-exporting its canonical counterpart."""

    def __init__(self, fullname: str, canonical: str | None, *, is_package: bool) -> None:
        self.fullname = fullname
        self.canonical = canonical
        self.is_package = is_package

    def create_module(self, spec: importlib.machinery.ModuleSpec) -> types.ModuleType | None:
        return None  # default module creation

    def exec_module(self, module: types.ModuleType) -> None:
        if self.is_package:
            # Allow attribute imports of child facades (e.g. resilience.circuit_breaker).
            module.__path__ = []  # type: ignore[attr-defined]

        if self.canonical is None:
            # Structural parent only (no direct canonical package mapping).
            module.__doc__ = f"Deprecated facade namespace for {self.fullname}."
            return

        warn_facade(self.fullname, self.canonical)
        canonical = importlib.import_module(self.canonical)
        names = getattr(canonical, "__all__", None)
        if names is None:
            names = [n for n in dir(canonical) if not n.startswith("_")]
        for name in names:
            try:
                setattr(module, name, getattr(canonical, name))
            except AttributeError:
                continue
        module.__doc__ = (
            f"Deprecated facade for {self.fullname}; use {self.canonical} instead."
        )
        module.__facade_canonical__ = self.canonical  # type: ignore[attr-defined]
        module.__all__ = list(names)  # type: ignore[attr-defined]


class _FacadeFinder(importlib.abc.MetaPathFinder):
    def find_spec(
        self,
        fullname: str,
        path: object = None,
        target: types.ModuleType | None = None,
    ) -> importlib.machinery.ModuleSpec | None:
        if not fullname.startswith("tradex.runtime."):
            return None

        canonical = FACADE_TO_CANONICAL.get(fullname)
        is_package = _has_facade_children(fullname)
        if canonical is None and not is_package:
            return None

        loader = _FacadeLoader(fullname, canonical, is_package=is_package)
        spec = importlib.machinery.ModuleSpec(
            fullname,
            loader,
            is_package=is_package,
        )
        if is_package:
            # Required so importlib allows child modules under this package.
            spec.submodule_search_locations = []
        return spec


def _install_finder() -> None:
    for finder in sys.meta_path:
        if isinstance(finder, _FacadeFinder):
            return
    # Insert near front so facades resolve before path-based failures
    sys.meta_path.insert(0, _FacadeFinder())


_install_finder()

warn_facade(__name__, "domain / application / infrastructure / runtime modules")

# Package-level lazy attributes (canonical direct — no intermediate facade file)
_LAZY_EXPORTS: dict[str, tuple[str, str]] = {
    "BrokerRouter": ("application.composer.router", "BrokerRouter"),
    "StreamOrchestrator": ("application.streaming.orchestrator", "StreamOrchestrator"),
    "BrokerCapabilities": ("domain.capabilities.broker_capabilities", "BrokerCapabilities"),
    "CapabilityDescriptor": ("domain.capabilities.broker_capabilities", "CapabilityDescriptor"),
    "BrokerRegistry": ("application.composer.registry", "BrokerRegistry"),
    "RoutingPolicy": ("domain.policies.source_selection", "RoutingPolicy"),
    "SourceSelectionPolicy": ("domain.policies.source_selection", "SourceSelectionPolicy"),
    "QuotaScheduler": ("application.scheduling.quota_scheduler", "QuotaScheduler"),
    "HistoricalDataCoordinator": (
        "application.data.historical_coordinator",
        "HistoricalDataCoordinator",
    ),
    "create_data_adapter": ("infrastructure.adapter_factory", "create_data_adapter"),
    "create_execution_provider": (
        "infrastructure.adapter_factory",
        "create_execution_provider",
    ),
    "create_broker_adapter": (
        "infrastructure.adapter_factory",
        "create_broker_adapter",
    ),
}

__all__ = list(_LAZY_EXPORTS) + ["FACADE_TO_CANONICAL"]


def __getattr__(name: str):
    if name == "FACADE_TO_CANONICAL":
        return FACADE_TO_CANONICAL
    if name not in _LAZY_EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attr = _LAZY_EXPORTS[name]
    warn_facade(f"tradex.runtime.{name}", f"{module_name}.{attr}")
    module = importlib.import_module(module_name)
    value = getattr(module, attr)
    globals()[name] = value
    return value
