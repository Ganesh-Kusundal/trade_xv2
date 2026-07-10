"""Capability surface types — pure dataclasses, no I/O."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from domain.capabilities import Capability

DataSource = Literal["live_broker", "datalake", "oms", "none", "mixed"]
Tier = Literal["core", "extended", "broker_only"]
Severity = Literal["P0", "P1", "P2", "P3"]
ExposureStatus = Literal["exposed", "gap", "broker_only", "partial", "mismatch"]


@dataclass(frozen=True)
class CliExposure:
    """CLI command that exercises a capability."""

    command: str
    module: str


@dataclass(frozen=True)
class RestExposure:
    """REST route that exercises a capability."""

    method: str
    path: str
    module: str
    data_source: DataSource


@dataclass(frozen=True)
class BrokerMethodRef:
    """Broker-layer method reference (connection-relative or module path)."""

    dhan: str | None = None
    upstox: str | None = None
    dhan_gateway: bool = True
    upstox_gateway: bool = True
    upstox_known_gap: str | None = None


@dataclass(frozen=True)
class CapabilitySurface:
    """One auditable capability surface."""

    id: str
    capability: Capability | None
    gateway_method: str | None
    abc_required: bool = False
    extended_only: bool = False
    broker: BrokerMethodRef = field(default_factory=BrokerMethodRef)
    cli: tuple[CliExposure, ...] = ()
    rest: tuple[RestExposure, ...] = ()
    cli_data_source: DataSource = "live_broker"
    tier: Tier = "core"
    broker_only_reason: str | None = None
    severity_if_gap: Severity = "P2"
    notes: str = ""


def surface(
    id: str,
    capability: Capability | None = None,
    gateway_method: str | None = None,
    *,
    abc_required: bool = False,
    extended_only: bool = False,
    dhan: str | None = None,
    upstox: str | None = None,
    dhan_gateway: bool = True,
    upstox_gateway: bool = True,
    upstox_known_gap: str | None = None,
    broker: BrokerMethodRef | None = None,
    cli: tuple[CliExposure | tuple[str, str], ...] = (),
    rest: tuple[RestExposure | tuple[str, str, str, str], ...] = (),
    cli_data_source: DataSource = "live_broker",
    tier: Tier = "core",
    broker_only_reason: str | None = None,
    severity_if_gap: Severity = "P2",
    notes: str = "",
) -> CapabilitySurface:
    """Build a surface; accept short CLI/REST tuples to cut catalog noise."""
    if broker is None:
        broker = BrokerMethodRef(
            dhan=dhan,
            upstox=upstox,
            dhan_gateway=dhan_gateway,
            upstox_gateway=upstox_gateway,
            upstox_known_gap=upstox_known_gap,
        )
    cli_t = tuple(c if isinstance(c, CliExposure) else CliExposure(c[0], c[1]) for c in cli)
    rest_t = tuple(
        r if isinstance(r, RestExposure) else RestExposure(r[0], r[1], r[2], r[3])  # type: ignore[arg-type]
        for r in rest
    )
    return CapabilitySurface(
        id=id,
        capability=capability,
        gateway_method=gateway_method,
        abc_required=abc_required,
        extended_only=extended_only,
        broker=broker,
        cli=cli_t,
        rest=rest_t,
        cli_data_source=cli_data_source,
        tier=tier,
        broker_only_reason=broker_only_reason,
        severity_if_gap=severity_if_gap,
        notes=notes,
    )
