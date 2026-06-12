"""Dhan futures instrument adapter."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from brokers.common.api.ports import FuturesProvider
from brokers.dhan.instrument_service import InstrumentService
from brokers.dhan.mapper.instruments import DhanInstrumentDefinition

COMMON_COMMODITIES = {
    "ALUMINIUM",
    "COPPER",
    "CRUDEOIL",
    "GOLD",
    "NATURALGAS",
    "SILVER",
    "ZINC",
    "LEAD",
    "NICKEL",
    "SILVERMIC",
}


class DhanFuturesAdapter(FuturesProvider):
    """Dhan futures contract lookup over the instrument service."""

    def __init__(self, instrument_service: InstrumentService) -> None:
        self._instrument_service = instrument_service

    def get_contracts(
        self, underlying: str, exchange_segment: Any
    ) -> list[DhanInstrumentDefinition]:
        del exchange_segment
        return self._instrument_service.get_futures(underlying)

    def get_nearest_contract(
        self, underlying: str, exchange_segment: Any
    ) -> DhanInstrumentDefinition:
        del exchange_segment
        contracts = self._instrument_service.get_futures(underlying)
        if not contracts:
            raise ValueError(f"No futures contract found for {underlying}")
        return contracts[0]

    def get_expiries(self, underlying: str, exchange_segment: Any) -> list[str | None]:
        del exchange_segment
        return [contract.expiry for contract in self._instrument_service.get_futures(underlying)]

    def is_commodity(self, underlying: str) -> bool:
        return underlying is not None and underlying.strip().upper() in COMMON_COMMODITIES

    def _is_future(self, definition: DhanInstrumentDefinition) -> bool:
        return definition.instrument_type.upper() in {"FUTURES", "FUT"}

    def _expiry_sort_key(self, expiry: str | None) -> str:
        if not expiry:
            return "9999-12-31"
        try:
            return datetime.fromisoformat(expiry).date().isoformat()
        except ValueError:
            return expiry
