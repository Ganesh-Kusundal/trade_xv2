"""InstrumentFactory — creates InstrumentAggregate instances from raw data.

Centralizes instrument construction with proper defaults, replacing
scattered ``InstrumentAggregate(...)`` calls throughout the codebase.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from domain.aggregates.instrument import InstrumentAggregate
from domain.instruments.instrument_id import InstrumentId


class InstrumentFactory:
    """Factory for creating InstrumentAggregate instances."""

    @staticmethod
    def create_equity(
        symbol: str,
        exchange: str,
        *,
        data_provider: Any | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> InstrumentAggregate:
        iid = InstrumentId.equity(exchange, symbol)
        return InstrumentAggregate(iid, data_provider=data_provider, metadata=metadata)

    @staticmethod
    def create_index(
        symbol: str,
        exchange: str,
        *,
        data_provider: Any | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> InstrumentAggregate:
        iid = InstrumentId.index(exchange, symbol)
        return InstrumentAggregate(iid, data_provider=data_provider, metadata=metadata)

    @staticmethod
    def create_future(
        symbol: str,
        exchange: str,
        expiry: date,
        *,
        data_provider: Any | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> InstrumentAggregate:
        iid = InstrumentId.future(exchange, symbol, expiry)
        return InstrumentAggregate(iid, data_provider=data_provider, metadata=metadata)

    @staticmethod
    def create_option(
        symbol: str,
        exchange: str,
        expiry: date,
        strike: Decimal | float | int,
        right: str,
        *,
        data_provider: Any | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> InstrumentAggregate:
        iid = InstrumentId.option(exchange, symbol, expiry, strike, right)
        return InstrumentAggregate(iid, data_provider=data_provider, metadata=metadata)
