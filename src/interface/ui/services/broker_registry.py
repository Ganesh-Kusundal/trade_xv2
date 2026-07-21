"""Broker registry — UI facade over composition-root accessors (TOS-P5-002).

Canonical gateway construction: ``infrastructure.gateway.factory``.
Concrete broker **types** are resolved only via ``runtime.broker_accessors``
so this UI module never imports ``brokers.providers.dhan`` / ``upstox`` / ``paper``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from domain.enums import BrokerId
from domain.market_enums import ExchangeId
from infrastructure.connection.authenticated_readiness import (
    authenticated_readiness_probe,
)
from infrastructure.gateway.factory import (
    ENV_FILES,
    bootstrap_gateway,
    env_files,
    list_available_brokers,
    require_gateway,
    resolve_env_path,
)
from runtime.broker_accessors import (
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

if TYPE_CHECKING:
    from domain.extensions.base import Extension
    from domain.instruments.instrument import Instrument
    from domain.ports.protocols import DataProvider

# Concrete broker symbols the CLI references — resolved through accessors.
AccountConnectionRegistry = get_dhan_account_registry_class()
DhanWireAdapter = get_dhan_broker_gateway_class()
InstrumentLoader = get_dhan_instrument_loader_class()
create_reconciliation_service = get_dhan_reconciliation_service_fn()
DhanSymbolValidator = get_dhan_symbol_validator_class()
PaperBrokerGateway = get_paper_gateway_class()
UpstoxDomainMapper = get_upstox_domain_mapper_class()
create_demo_broker = create_seeded_mock_broker


def get_market_provider(broker: str = "dhan") -> DataProvider | None:
    """Return a domain ``DataProvider`` for *broker* (broker-as-plugin)."""
    result = bootstrap_gateway(broker, skip_auth_probe=True)
    if not result.ok or result.gateway is None:
        return None
    return result.gateway


def get_broker_extensions(broker: str, gateway: object) -> list[Extension]:
    if broker == BrokerId.DHAN:
        return get_dhan_extensions(gateway)
    return []


def create_instrument(
    broker: str,
    symbol: str,
    exchange: str = ExchangeId.NSE,
) -> Instrument | None:
    result = bootstrap_gateway(broker, skip_auth_probe=True)
    if not result.ok or result.gateway is None:
        return None

    provider = result.gateway
    extensions = get_broker_extensions(broker, result.gateway)

    from domain.instruments.instrument import Equity

    inst = Equity(symbol, exchange, provider=provider, metadata={"broker": broker})
    inst.aggregate._extensions = extensions  # type: ignore[attr-defined]
    return inst


__all__ = [
    "ENV_FILES",
    "AccountConnectionRegistry",
    "DhanWireAdapter",
    "DhanSymbolValidator",
    "InstrumentLoader",
    "PaperBrokerGateway",
    "UpstoxDomainMapper",
    "authenticated_readiness_probe",
    "bootstrap_gateway",
    "create_demo_broker",
    "create_instrument",
    "create_reconciliation_service",
    "create_seeded_mock_broker",
    "env_files",
    "get_broker_extensions",
    "get_dhan_account_registry_class",
    "get_dhan_broker_gateway_class",
    "get_dhan_extensions",
    "get_dhan_instrument_loader_class",
    "get_dhan_reconciliation_service_factory",
    "get_dhan_reconciliation_service_fn",
    "get_dhan_symbol_validator_class",
    "get_dhan_websocket_classes",
    "get_market_provider",
    "get_mock_broker_class",
    "get_paper_gateway_class",
    "get_upstox_domain_mapper_class",
    "get_upstox_reconciliation_service_factory",
    "list_available_brokers",
    "require_gateway",
    "resolve_env_path",
]
