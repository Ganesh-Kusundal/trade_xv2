"""Concrete broker type accessors — composition-root only (TOS-P5-002 / DR-B4).

Presentation layers (``interface.ui``) must not import ``brokers.providers.dhan`` /
``brokers.providers.upstox`` / ``brokers.providers.paper`` by name. They call these accessors
(or re-exports on ``interface.ui.services.broker_registry``) instead.

This module lives under ``runtime/`` (composition root), which is the
sanctioned place to name concrete broker packages.
"""

from __future__ import annotations

from typing import Any

__all__ = [
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
]


def get_paper_gateway_class() -> type:
    """Return the :class:`PaperGateway` class."""
    from brokers.providers.paper import PaperGateway

    return PaperGateway


def get_mock_broker_class() -> type:
    """Return the paper gateway class used as a mock broker."""
    from brokers.providers.paper import PaperGateway

    return PaperGateway


def create_seeded_mock_broker(name: str = "dhan") -> Any:
    """Return a PaperGateway instance with default capital."""
    from brokers.providers.paper import PaperGateway

    return PaperGateway()


def get_dhan_websocket_classes() -> tuple[type, type]:
    """Return ``(DhanMarketFeed, DhanOrderStream)``."""
    from brokers.providers.dhan.websocket import DhanMarketFeed, DhanOrderStream

    return DhanMarketFeed, DhanOrderStream


def get_dhan_reconciliation_service_factory():
    """Return Dhan reconciliation service class."""
    from brokers.providers.dhan.portfolio.reconciliation import DhanReconciliationService

    return DhanReconciliationService


def get_dhan_reconciliation_service_fn():
    """Return the Dhan ``create_reconciliation_service`` factory function."""
    from brokers.providers.dhan.portfolio.reconciliation import create_reconciliation_service

    return create_reconciliation_service


def get_dhan_account_registry_class() -> type:
    """Return ``AccountConnectionRegistry``."""
    from brokers.providers.dhan.identity.account_registry import AccountConnectionRegistry

    return AccountConnectionRegistry


def get_dhan_broker_gateway_class() -> type:
    """Return ``DhanWireAdapter``."""
    from brokers.providers.dhan.wire import DhanWireAdapter

    return DhanWireAdapter


def get_dhan_instrument_loader_class() -> type:
    """Return ``InstrumentLoader``."""
    from brokers.providers.dhan.loader import InstrumentLoader

    return InstrumentLoader


def get_dhan_symbol_validator_class() -> type:
    """Return ``DhanSymbolValidator``."""
    from brokers.providers.dhan.symbol_validator import DhanSymbolValidator

    return DhanSymbolValidator


def get_upstox_domain_mapper_class() -> type:
    """Return ``UpstoxDomainMapper``."""
    from brokers.providers.upstox.mappers.domain_mapper import UpstoxDomainMapper

    return UpstoxDomainMapper


def get_upstox_reconciliation_service_factory():
    """Return Upstox reconciliation service factory callable."""
    from brokers.providers.upstox.reconciliation.service import create_reconciliation_service

    return create_reconciliation_service


def get_dhan_extensions(gateway: object) -> list:
    """Return Dhan depth extensions attached to *gateway*."""
    from brokers.providers.dhan.extensions.depth20 import DhanDepth20Extension
    from brokers.providers.dhan.extensions.depth200 import DhanDepth200Extension

    return [DhanDepth20Extension(gateway), DhanDepth200Extension(gateway)]
