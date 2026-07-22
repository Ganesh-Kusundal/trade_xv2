"""Unit tests for ContractHistoricalCoordinator lane detection."""

from __future__ import annotations

from datetime import date

from application.data.contract_historical_coordinator import _asset_kind, _is_rolling_index_lane
from domain.candles.contract_historical import ContractHistoricalQuery
from domain.historical.contract_state import ContractState
from domain.instruments.asset_kind import AssetKind
from domain.instruments.instrument_id import InstrumentId


def test_rolling_lane_for_expired_nfo_index_without_upstox_key() -> None:
    query = ContractHistoricalQuery(
        instrument=InstrumentId.parse("NFO:NIFTY:20250102:24000:CE"),
        from_date=date(2024, 12, 1),
        to_date=date(2024, 12, 5),
        timeframe="5m",
        contract_state=ContractState.EXPIRED,
    )
    assert _is_rolling_index_lane(query, ContractState.EXPIRED) is True


def test_exact_expired_lane_when_upstox_key_present() -> None:
    query = ContractHistoricalQuery(
        instrument=InstrumentId.parse("NFO:NIFTY:20250102:24000:CE"),
        from_date=date(2024, 12, 1),
        to_date=date(2024, 12, 5),
        timeframe="5m",
        contract_state=ContractState.EXPIRED,
        expired_instrument_key="NFO_FO|12345",
    )
    assert _is_rolling_index_lane(query, ContractState.EXPIRED) is False


def test_no_rolling_lane_for_equity() -> None:
    query = ContractHistoricalQuery(
        instrument=InstrumentId.equity("NSE", "RELIANCE"),
        from_date=date(2024, 12, 1),
        to_date=date(2024, 12, 5),
        contract_state=ContractState.ACTIVE,
    )
    assert _is_rolling_index_lane(query, ContractState.ACTIVE) is False


def test_mcx_commodity_future_routes_as_futures() -> None:
    iid = InstrumentId.future("MCX", "GOLD", date(2026, 6, 5))
    assert iid.kind == AssetKind.COMMODITY.value
    assert _asset_kind(iid) == AssetKind.FUTURES
