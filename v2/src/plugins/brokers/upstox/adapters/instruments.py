"""Upstox instruments adapter."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from domain.entities import Instrument
from domain.enums import AssetClass, ExchangeId, InstrumentType
from domain.value_objects import InstrumentId
from plugins.brokers.upstox.wire import UpstoxWire

if TYPE_CHECKING:
    from plugins.brokers.common.transport import BaseTransport


class UpstoxInstrumentAdapter:
    def __init__(self, transport: BaseTransport, wire: UpstoxWire | None = None) -> None:
        self._transport = transport
        self._wire = wire or UpstoxWire()
        self._by_id: dict[str, Instrument] = {}

    def load_instruments(self) -> list[Instrument]:
        data = self._transport.get("/market-quote/quotes")  # ponytail: master dump via CDN in prod
        rows = data if isinstance(data, list) else data.get("data", [])
        if isinstance(rows, dict):
            rows = [{"instrument_key": k, **v} for k, v in rows.items()]
        out: list[Instrument] = []
        for row in rows:
            inst = self._to_instrument(row)
            self._by_id[inst.instrument_id.value] = inst
            key = str(row.get("instrument_key") or row.get("instrument_token") or "")
            if key:
                self._wire.register_key(inst.instrument_id, key)
            out.append(inst)
        return out

    def search(self, query: str) -> list[Instrument]:
        q = query.upper()
        return [i for i in self._by_id.values() if q in i.symbol.upper()]

    def _to_instrument(self, row: dict[str, Any]) -> Instrument:
        key = str(row.get("instrument_key") or row.get("tradingsymbol") or "")
        symbol = str(row.get("trading_symbol") or row.get("tradingsymbol") or key.split(":")[-1])
        exch = ExchangeId.NSE if "NSE" in key.upper() else ExchangeId.BSE
        iid = InstrumentId(value=f"{exch.name}:{symbol}")
        return Instrument(
            instrument_id=iid,
            symbol=symbol,
            exchange=exch,
            asset_class=AssetClass.EQUITY,
            currency="INR",
            instrument_type=InstrumentType.EQUITY,
        )
