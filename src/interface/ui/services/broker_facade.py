"""Composition-root facade for the CLI layer.

Per the FDOS inversion, brokers are plugins: the public surface is ``markets``
and the domain ports (``DataProvider`` / ``ExecutionProvider``), not broker
gateways. CLI modules pull broker-specific pieces from HERE, never from a
concrete broker package directly. This module re-exports the broker symbols the
CLI needs, but reaches every concrete broker type through
:mod:`interface.ui.services.broker_registry` (the single sanctioned
concrete-broker importer within the UI layer) rather than naming a broker
package by name. See the ``cli-no-broker-impl`` import-linter contract.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

# ── Re-exports of broker internals the CLI legitimately needs ────────────────
# Every concrete broker type is reached via broker_registry accessor functions
# (the sanctioned indirection), never by naming a broker package directly.
from interface.ui.services.broker_registry import (
    bootstrap_gateway,
    create_seeded_mock_broker as create_demo_broker,
    get_dhan_account_registry_class,
    get_dhan_broker_gateway_class,
    get_dhan_extensions,
    get_dhan_instrument_loader_class,
    get_dhan_reconciliation_service_fn,
    get_dhan_symbol_validator_class,
    get_paper_gateway_class,
    get_upstox_domain_mapper_class,
)

if TYPE_CHECKING:
    from domain.extensions.base import Extension
    from domain.instruments.instrument import Instrument
    from domain.ports.protocols import DataProvider

# Concrete broker symbols the CLI references — resolved through the registry so
# this module never imports a broker package by name.
AccountConnectionRegistry = get_dhan_account_registry_class()
DhanBrokerGateway = get_dhan_broker_gateway_class()
InstrumentLoader = get_dhan_instrument_loader_class()
create_reconciliation_service = get_dhan_reconciliation_service_fn()
DhanSymbolValidator = get_dhan_symbol_validator_class()
PaperBrokerGateway = get_paper_gateway_class()
UpstoxDomainMapper = get_upstox_domain_mapper_class()


def get_market_provider(broker: str = "dhan") -> "DataProvider | None":
    """Return a domain ``DataProvider`` for *broker* (broker-as-plugin).

    Dhan is fully adapted via its domain data adapter.
    Upstox/Zerodha/IB adapters land in P7; today they return their gateway,
    which callers can wrap once the adapter exists.
    """
    result = bootstrap_gateway(
        broker,
        skip_auth_probe=True,  # analytics composition; no TOTP burn
    )
    if not result.ok or result.gateway is None:
        return None
    # BrokerAdapter satisfies DataProvider structurally
    return result.gateway


def get_broker_extensions(broker: str, gateway: object) -> "list[Extension]":
    """Return domain ``Extension`` instances for *broker*.

    These are the broker-specific capability plugins (depth_20, depth_200,
    super_orders, etc.) that get attached to instruments. Domain code
    discovers them via ``instrument.get_extension("depth20")``.
    """
    if broker == "dhan":
        return get_dhan_extensions(gateway)
    return []


def create_instrument(
    broker: str,
    symbol: str,
    exchange: str = "NSE",
) -> "Instrument | None":
    """Fully-wired instrument with provider + broker extensions (composition root).

    Returns an ``Instrument`` (Equity by default) with:
    - A domain ``DataProvider`` adapter wrapping the broker gateway
    - Broker-specific extensions (depth_20, depth_200, etc.) registered

    Returns ``None`` if the broker cannot be bootstrapped (no creds, offline).
    """
    result = bootstrap_gateway(
        broker,
        skip_auth_probe=True,  # instrument wire-up; no TOTP burn
    )
    if not result.ok or result.gateway is None:
        return None

    # Build the DataProvider adapter — BrokerAdapter satisfies DataProvider structurally
    provider = result.gateway

    # Build the broker extensions
    extensions = get_broker_extensions(broker, result.gateway)

    # Create the instrument
    from domain.instruments.instrument_id import InstrumentId
    from domain.instruments.instrument import Equity

    inst = Equity(symbol, exchange, provider=provider, metadata={"broker": broker})
    # Attach extensions to the underlying aggregate
    inst.aggregate._extensions = extensions  # type: ignore[attr-defined]
    return inst
