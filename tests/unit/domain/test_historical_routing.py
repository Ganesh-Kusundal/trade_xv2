"""Unit tests for lane-based historical routing (ADR-0023)."""

from __future__ import annotations

from datetime import date

from domain.capabilities.historical_routing import (
    HistoricalRouteConstraint,
    can_serve_historical_lane,
)
from domain.capabilities.broker_capabilities import HistoricalWindowConstraint
from domain.historical.contract_state import ContractState
from domain.historical.route_lane import HistoricalRouteLane
from domain.instruments.asset_kind import AssetKind


def test_dhan_serves_nfo_rolling_expired_index_options() -> None:
    lane = HistoricalRouteLane(
        asset_kind=AssetKind.OPTIONS,
        exchange="NFO",
        contract_state=ContractState.EXPIRED,
        timeframe="5m",
        lookback_days=7,
        underlying="NIFTY",
        rolling_index_options=True,
    )
    routes = (
        HistoricalRouteConstraint(
            AssetKind.OPTIONS,
            "NFO",
            frozenset({ContractState.EXPIRED}),
            exact_contract=False,
            rolling_index_options=True,
        ),
    )
    windows = (HistoricalWindowConstraint(timeframe="5m", max_lookback_days=365, max_chunk_days=90),)
    assert can_serve_historical_lane(
        supports_historical_data=True,
        historical_routes=routes,
        historical_windows=windows,
        lane=lane,
    )


def test_upstox_expired_requires_plus_entitlement() -> None:
    lane = HistoricalRouteLane(
        asset_kind=AssetKind.OPTIONS,
        exchange="NFO",
        contract_state=ContractState.EXPIRED,
        timeframe="5m",
        lookback_days=7,
        underlying="NIFTY",
    )
    routes = (
        HistoricalRouteConstraint(
            AssetKind.OPTIONS,
            "NFO",
            frozenset({ContractState.EXPIRED, ContractState.AUTO}),
            requires_entitlement="upstox_plus",
        ),
    )
    windows = (HistoricalWindowConstraint(timeframe="5m", max_lookback_days=30, max_chunk_days=30),)
    assert not can_serve_historical_lane(
        supports_historical_data=True,
        historical_routes=routes,
        historical_windows=windows,
        lane=lane,
        entitlements=frozenset(),
    )
    assert can_serve_historical_lane(
        supports_historical_data=True,
        historical_routes=routes,
        historical_windows=windows,
        lane=lane,
        entitlements=frozenset({"upstox_plus"}),
    )


def test_lookback_window_rejects_oversized_request() -> None:
    lane = HistoricalRouteLane(
        asset_kind=AssetKind.EQUITY,
        exchange="NSE",
        contract_state=ContractState.ACTIVE,
        timeframe="5m",
        lookback_days=400,
        underlying="RELIANCE",
    )
    routes = (HistoricalRouteConstraint(AssetKind.EQUITY, "NSE", frozenset({ContractState.ACTIVE})),)
    windows = (HistoricalWindowConstraint(timeframe="5m", max_lookback_days=30, max_chunk_days=30),)
    assert not can_serve_historical_lane(
        supports_historical_data=True,
        historical_routes=routes,
        historical_windows=windows,
        lane=lane,
    )


def test_mcx_commodity_future_matches_futures_route() -> None:
    """InstrumentId.future(MCX) stores COMMODITY kind; routing lane uses FUTURES."""
    from application.data.contract_historical_coordinator import _asset_kind
    from domain.instruments.instrument_id import InstrumentId

    iid = InstrumentId.future("MCX", "GOLD", date(2026, 6, 5))
    lane = HistoricalRouteLane(
        asset_kind=_asset_kind(iid),
        exchange="MCX",
        contract_state=ContractState.ACTIVE,
        timeframe="5m",
        lookback_days=7,
        underlying="GOLD",
    )
    routes = (
        HistoricalRouteConstraint(AssetKind.FUTURES, "MCX", frozenset({ContractState.ACTIVE})),
    )
    windows = (HistoricalWindowConstraint(timeframe="5m", max_lookback_days=365, max_chunk_days=90),)
    assert can_serve_historical_lane(
        supports_historical_data=True,
        historical_routes=routes,
        historical_windows=windows,
        lane=lane,
    )
