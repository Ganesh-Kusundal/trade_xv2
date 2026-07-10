"""Query helpers over CAPABILITY_SURFACES."""

from __future__ import annotations

from domain.capabilities import Capability
from domain.capability_manifest.catalog import CAPABILITY_SURFACES
from domain.capability_manifest.types import CapabilitySurface, ExposureStatus

# Frozen snapshot of MarketDataGateway / BrokerAdapter abstract surface.
# Kept explicit (not inspect-derived) so domain catalog tests stay free of
# protocol-introspection quirks and remain a deliberate coverage contract.
_ABC_GATEWAY_METHODS: frozenset[str] = frozenset(
    {
        "cancel_order",
        "capabilities",
        "close",
        "depth",
        "describe",
        "funds",
        "future_chain",
        "get_orderbook",
        "get_trade_book",
        "history",
        "history_batch",
        "holdings",
        "load_instruments",
        "ltp",
        "ltp_batch",
        "option_chain",
        "place_order",
        "positions",
        "quote",
        "quote_batch",
        "search",
        "stream",
        "stream_depth",
        "stream_order",
        "trades",
    }
)


def all_surfaces() -> tuple[CapabilitySurface, ...]:
    """Return all registered capability surfaces."""
    return CAPABILITY_SURFACES


def surface_by_id(surface_id: str) -> CapabilitySurface | None:
    """Lookup a surface by id."""
    return _BY_ID.get(surface_id)


def surfaces_for_capability(cap: Capability) -> list[CapabilitySurface]:
    """Return all surfaces mapped to a capability enum value."""
    return [s for s in CAPABILITY_SURFACES if s.capability == cap]


def abc_gateway_methods() -> frozenset[str]:
    """Abstract methods required by the broker adapter gateway surface."""
    return _ABC_GATEWAY_METHODS


def all_capability_enum_values() -> frozenset[Capability]:
    """All domain Capability enum members."""
    return frozenset(Capability)


def mapped_capability_values() -> frozenset[Capability]:
    """Capability enum values referenced by at least one surface."""
    return frozenset(s.capability for s in CAPABILITY_SURFACES if s.capability is not None)


def broker_only_capabilities() -> frozenset[Capability]:
    """Capabilities explicitly marked broker_only on their primary surface."""
    return frozenset(
        s.capability
        for s in CAPABILITY_SURFACES
        if s.capability is not None and s.tier == "broker_only"
    )


def classify_exposure(surface: CapabilitySurface) -> ExposureStatus:
    """Classify whether a surface is fully exposed across layers."""
    if surface.tier == "broker_only" or surface.broker_only_reason:
        return "broker_only"
    has_cli = bool(surface.cli)
    has_rest = bool(surface.rest)
    if has_cli and has_rest:
        cli_src = surface.cli_data_source
        rest_sources = {r.data_source for r in surface.rest}
        if cli_src == "live_broker" and rest_sources <= {"datalake", "oms"}:
            return "mismatch"
        return "exposed"
    if has_cli or has_rest:
        return "partial"
    if surface.broker.dhan or surface.broker.upstox:
        return "gap"
    return "broker_only"


_BY_ID: dict[str, CapabilitySurface] = {s.id: s for s in CAPABILITY_SURFACES}
