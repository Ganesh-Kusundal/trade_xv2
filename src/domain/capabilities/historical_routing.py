"""Historical route constraints — lane eligibility for broker routing (ADR-0023)."""

from __future__ import annotations

from dataclasses import dataclass

from domain.historical.contract_state import ContractState
from domain.historical.route_lane import HistoricalRouteLane
from domain.instruments.asset_kind import AssetKind


@dataclass(frozen=True)
class HistoricalRouteConstraint:
    """One broker-supported historical fetch lane."""

    asset_kind: AssetKind
    exchange: str
    contract_states: frozenset[ContractState]
    exact_contract: bool = True
    rolling_index_options: bool = False
    requires_entitlement: str | None = None  # e.g. "upstox_plus"


def _normalize_timeframe(timeframe: str) -> str:
    t = timeframe.strip()
    if t.lower() in {"1d", "day"}:
        return "1D"
    return t


def can_serve_historical_lane(
    *,
    supports_historical_data: bool,
    historical_routes: tuple[HistoricalRouteConstraint, ...],
    historical_windows: tuple,
    lane: HistoricalRouteLane,
    entitlements: frozenset[str] | None = None,
) -> bool:
    """Return True when capabilities + entitlements cover the requested lane."""
    if not supports_historical_data:
        return False
    if lane.lookback_days > 0:
        window_ok = False
        tf_lane = _normalize_timeframe(lane.timeframe)
        for w in historical_windows:
            tf = _normalize_timeframe(getattr(w, "timeframe", "") or "")
            max_lb = getattr(w, "max_lookback_days", 0)
            if tf == tf_lane and lane.lookback_days <= max_lb:
                window_ok = True
                break
        if not window_ok:
            return False

    ent = entitlements or frozenset()
    for route in historical_routes:
        if route.asset_kind != lane.asset_kind:
            continue
        if route.exchange != lane.exchange:
            continue
        if lane.contract_state not in route.contract_states:
            if lane.contract_state != ContractState.AUTO:
                continue
            if ContractState.AUTO not in route.contract_states and not route.contract_states:
                continue
        if route.rolling_index_options != lane.rolling_index_options:
            continue
        if route.exact_contract is False and not route.rolling_index_options:
            continue
        if route.exact_contract and lane.rolling_index_options:
            continue
        if route.requires_entitlement and route.requires_entitlement not in ent:
            continue
        return True
    return False
