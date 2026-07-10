"""Broker registry — unified factory for creating gateways.

Canonical implementation: ``infrastructure.gateway.factory``.
This module re-exports it so CLI code keeps existing import paths, and
adds class accessors that presentation layers need without importing
broker packages directly (import-linter).
"""

from __future__ import annotations

from typing import Any

from infrastructure.connection.authenticated_readiness import (  # noqa: F401
    authenticated_readiness_probe,
)
from infrastructure.gateway.factory import (  # noqa: F401
    ENV_FILES,
    bootstrap_gateway,
    create_gateway,
    list_available_brokers,
    require_gateway,
    resolve_env_path,
)

# Re-export probe so unit tests can monkeypatch at the registry boundary
# (bootstrap_gateway imports the probe lazily; patching this name only
# works if bootstrap also reads from here — prefer patching
# ``infrastructure.connection.authenticated_readiness.authenticated_readiness_probe``).

__all__ = [
    "ENV_FILES",
    "authenticated_readiness_probe",
    "bootstrap_gateway",
    "create_gateway",
    "create_seeded_mock_broker",
    "get_dhan_reconciliation_service_factory",
    "get_dhan_websocket_classes",
    "get_mock_broker_class",
    "get_paper_gateway_class",
    "list_available_brokers",
    "require_gateway",
    "resolve_env_path",
]


def get_paper_gateway_class() -> type:
    """Return the :class:`PaperGateway` class (no direct cli→brokers.paper import)."""
    from brokers.paper import PaperGateway

    return PaperGateway


def get_mock_broker_class() -> type:
    """Return the :class:`PaperGateway` class (mock broker replacement)."""
    from brokers.paper import PaperGateway

    return PaperGateway


def create_seeded_mock_broker(name: str = "dhan") -> Any:
    """Return a PaperGateway instance with default capital."""
    from brokers.paper import PaperGateway

    return PaperGateway()


def get_dhan_websocket_classes() -> tuple[type, type]:
    """Return ``(DhanMarketFeed, DhanOrderStream)`` without cli→brokers.dhan."""
    from brokers.dhan.websocket import DhanMarketFeed, DhanOrderStream

    return DhanMarketFeed, DhanOrderStream


def get_dhan_reconciliation_service_factory():
    """Return Dhan reconciliation service factory callable."""
    from brokers.dhan.portfolio.reconciliation import DhanReconciliationService

    return DhanReconciliationService
