"""Dhan instrument master loader + search."""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING, Any

from domain.entities import Instrument
from domain.enums import AssetClass, ExchangeId, InstrumentType
from domain.value_objects import InstrumentId
from plugins.brokers.dhan.wire import DhanWire

if TYPE_CHECKING:
    from plugins.brokers.common.transport import BaseTransport


class DhanInstrumentAdapter:
    def __init__(self, transport: BaseTransport, wire: DhanWire | None = None) -> None:
        self._transport = transport
        self._wire = wire or DhanWire()
        self._by_id: dict[str, Instrument] = {}

    def load_instruments(self) -> list[Instrument]:
        data = self._transport.get("/instrument")
        rows = data if isinstance(data, list) else data.get("data", [])
        out: list[Instrument] = []
        for row in rows:
            inst = self._to_instrument(row)
            self._by_id[inst.instrument_id.value] = inst
            sec = str(row.get("security_id") or row.get("securityId") or "")
            if sec:
                self._wire.register_security(inst.instrument_id, sec)
            out.append(inst)
        return out

    def search(self, query: str) -> list[Instrument]:
        q = query.upper()
        return [i for i in self._by_id.values() if q in i.symbol.upper() or q in i.instrument_id.value.upper()]

    def resolve(self, instrument_id: InstrumentId) -> Instrument | None:
        return self._by_id.get(instrument_id.value)

    def _to_instrument(self, row: dict[str, Any]) -> Instrument:
        symbol = str(row.get("trading_symbol") or row.get("symbol") or row.get("SEM_TRADING_SYMBOL") or "")
        exch = str(row.get("exchange") or row.get("SEM_EXM_EXCH_ID") or "NSE").upper()
        exchange = ExchangeId.NSE if "NSE" in exch else ExchangeId.BSE if "BSE" in exch else ExchangeId.NSE
        iid = InstrumentId(value=f"{exchange.name}:{symbol}" if symbol else str(row.get("security_id", "")))
        return Instrument(
            instrument_id=iid,
            symbol=symbol or iid.value,
            exchange=exchange,
            asset_class=AssetClass.EQUITY,
            currency="INR",
            instrument_type=InstrumentType.EQUITY,
            strike=Decimal(str(row["strike"])) if row.get("strike") else None,
        )
