"""Composition-root facade for the CLI layer (the sanctioned broker importer).

Per the FDOS inversion, brokers are plugins: the public surface is ``markets``
and the domain ports (``DataProvider`` / ``ExecutionProvider``), not broker
gateways. CLI modules must pull broker-specific pieces from HERE, never from
``brokers.dhan`` / ``brokers.upstox`` / ``brokers.paper`` directly. This module
is the single sanctioned ``brokers.*`` importer within ``cli`` (see the
``cli-no-broker-impl`` import-linter contract).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

# ── Re-exports of broker internals the CLI legitimately needs ────────────────
# These are the only broker symbols the CLI may reference; everything else
# flows through the domain ports below.
from brokers.dhan.identity.account_registry import AccountConnectionRegistry
from brokers.dhan.gateway import DhanBrokerGateway
from brokers.dhan.loader import InstrumentLoader
from brokers.dhan.reconciliation import create_reconciliation_service
from brokers.dhan.symbol_validator import DhanSymbolValidator
from cli.services.broker_registry import create_seeded_mock_broker as create_demo_broker
from brokers.paper.paper_gateway import PaperGateway as PaperBrokerGateway
from brokers.upstox.mappers.domain_mapper import UpstoxDomainMapper

if TYPE_CHECKING:
    from domain.extensions.base import Extension
    from domain.ports.protocols import DataProvider

    from domain.instruments.instrument import Instrument

from cli.services.broker_registry import bootstrap_gateway


def get_market_provider(broker: str = "dhan") -> "DataProvider | None":
    """Return a domain ``DataProvider`` for *broker* (broker-as-plugin).

    Dhan is fully adapted via :class:`brokers.dhan.adapter.DhanDataAdapter`.
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
        from brokers.dhan.extensions.depth20 import DhanDepth20Extension
        from brokers.dhan.extensions.depth200 import DhanDepth200Extension

        return [
            DhanDepth20Extension(gateway),
            DhanDepth200Extension(gateway),
        ]
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
