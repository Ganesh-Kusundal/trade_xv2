"""Broker registry — UI facade over composition-root accessors (TOS-P5-002).

Canonical gateway construction: ``infrastructure.gateway.factory``.
Concrete broker **types** are resolved only via ``runtime.broker_accessors``
so this UI module never imports ``brokers.dhan`` / ``upstox`` / ``paper``.
"""

from __future__ import annotations

from infrastructure.connection.authenticated_readiness import (  # noqa: F401
    authenticated_readiness_probe,
)
from infrastructure.gateway.factory import (  # noqa: F401
    ENV_FILES,
    bootstrap_gateway,
    env_files,
    list_available_brokers,
    require_gateway,
    resolve_env_path,
)
from runtime.broker_accessors import (  # noqa: F401
    create_seeded_mock_broker,
    get_dhan_account_registry_class,
    get_dhan_broker_gateway_class,
    get_dhan_extensions,
    get_dhan_instrument_loader_class,
    get_dhan_reconciliation_service_factory,
    get_dhan_reconciliation_service_fn,
    get_dhan_symbol_validator_class,
    get_dhan_websocket_classes,
    get_mock_broker_class,
    get_paper_gateway_class,
    get_upstox_domain_mapper_class,
    get_upstox_reconciliation_service_factory,
)

__all__ = [
    "ENV_FILES",
    "authenticated_readiness_probe",
    "bootstrap_gateway",
    "create_seeded_mock_broker",
    "get_dhan_account_registry_class",
    "get_dhan_broker_gateway_class",
    "get_dhan_extensions",
    "get_dhan_instrument_loader_class",
    "get_dhan_reconciliation_service_factory",
    "get_dhan_reconciliation_service_fn",
    "get_dhan_symbol_validator_class",
    "get_dhan_websocket_classes",
    "get_mock_broker_class",
    "get_paper_gateway_class",
    "get_upstox_domain_mapper_class",
    "get_upstox_reconciliation_service_factory",
    "list_available_brokers",
    "require_gateway",
    "resolve_env_path",
]
