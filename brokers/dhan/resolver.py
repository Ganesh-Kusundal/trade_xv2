"""O(1) symbol → Instrument resolver backed by dictionaries."""

from __future__ import annotations

import logging
import threading
from typing import Optional
from collections.abc import Iterable

from brokers.dhan.domain import Exchange, Instrument, InstrumentType, OptionType
from brokers.dhan.segments import SEGMENT_TO_EXCHANGE
from brokers.dhan.exceptions import InstrumentNotFoundError

logger = logging.getLogger(__name__)

_NAME_TO_TYPE: dict[str, InstrumentType] = {
    "EQUITY": InstrumentType.EQUITY,
    "INDEX": InstrumentType.EQUITY,
    "OPTIDX": InstrumentType.OPTION,
    "OPTSTK": InstrumentType.OPTION,
    "OPTCUR": InstrumentType.OPTION,
    "OPTFUT": InstrumentType.OPTION,
    "OPTCOM": InstrumentType.OPTION,
    "FUTIDX": InstrumentType.FUTURE,
    "FUTSTK": InstrumentType.FUTURE,
    "FUTCUR": InstrumentType.FUTURE,
    "FUTCOM": InstrumentType.FUTURE,
}

_DHAN_OPTION_TYPE: dict[str, OptionType] = {
    "CE": OptionType.CALL, "CALL": OptionType.CALL,
    "PE": OptionType.PUT, "PUT": OptionType.PUT,
}


class SymbolResolver:
    """Thread-safe O(1) symbol → Instrument resolver."""

    def __init__(self) -> None:
        self._by_symbol: dict[tuple[str, Exchange], Instrument] = {}
        self._by_security_id: dict[str, Instrument] = {}
        self._by_underlying: dict[tuple[str, Exchange], list[Instrument]] = {}
        self._loaded = False
        self._lock = threading.Lock()

    def resolve(self, symbol: str, exchange: str) -> Instrument:
        exch = self._normalise_exchange(exchange)
        inst = self._find(symbol, exch)
        if inst is None:
            raise InstrumentNotFoundError(
                f"Instrument not found: symbol={symbol!r}, exchange={exchange!r}"
            )
        return inst

    def get_by_symbol(self, symbol: str, exchange: str) -> Optional[Instrument]:
        try:
            return self._find(symbol, self._normalise_exchange(exchange))
        except Exception:
            return None

    def get_by_security_id(self, security_id: str) -> Optional[Instrument]:
        return self._by_security_id.get(str(security_id))

    def get_futures(self, underlying: str, exchange: str) -> list[Instrument]:
        exch = self._normalise_exchange(exchange)
        key = (underlying.strip().upper(), exch)
        contracts = self._by_underlying.get(key, [])
        return sorted(contracts, key=lambda i: (i.expiry or "9999-12-31"))

    def get_futures_expiries(self, underlying: str, exchange: str) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for c in self.get_futures(underlying, exchange):
            if c.expiry and c.expiry not in seen:
                seen.add(c.expiry)
                result.append(c.expiry)
        return result

    def get_lot_size(self, symbol: str, exchange: str) -> int:
        return self.resolve(symbol, exchange).lot_size

    def stats(self) -> dict:
        return {"loaded": self._loaded, "total": len(self._by_security_id)}

    def all_instruments(self) -> list[Instrument]:
        return list(self._by_security_id.values())

    def load_from_rows(self, rows: Iterable[dict]) -> None:
        new_by_symbol: dict[tuple[str, Exchange], Instrument] = {}
        new_by_sid: dict[str, Instrument] = {}
        new_by_underlying: dict[tuple[str, Exchange], list[Instrument]] = {}
        skipped = 0

        for row in rows:
            try:
                inst = self._row_to_instrument(row)
            except Exception:
                skipped += 1
                continue

            if inst is None:
                skipped += 1
                continue

            # Index by trading symbol
            new_by_symbol[(inst.symbol.upper(), inst.exchange)] = inst
            # Index by canonical symbol if different
            if inst.canonical_symbol and inst.canonical_symbol.upper() != inst.symbol.upper():
                new_by_symbol[(inst.canonical_symbol.upper(), inst.exchange)] = inst
            # Stripped form
            stripped = inst.symbol.upper().replace(" ", "").replace("-", "").replace("_", "")
            new_by_symbol[(stripped, inst.exchange)] = inst
            # CE/PE alternate forms for options
            if inst.is_option and inst.option_type and inst.expiry and inst.underlying:
                try:
                    from datetime import datetime
                    dt = datetime.strptime(inst.expiry[:10], "%Y-%m-%d")
                    exp_str = dt.strftime("%d %b").upper()
                    strike_str = str(int(inst.strike_price)) if inst.strike_price and inst.strike_price % 1 == 0 else str(inst.strike_price)
                    ce_pe = "CE" if inst.option_type == OptionType.CALL else "PE"
                    key_spaced = (f"{inst.underlying} {exp_str} {strike_str} {ce_pe}".upper(), inst.exchange)
                    new_by_symbol[key_spaced] = inst
                    key_compact = (f"{inst.underlying}{exp_str}{strike_str}{ce_pe}".replace(" ", "").upper(), inst.exchange)
                    new_by_symbol[key_compact] = inst
                except Exception:
                    pass

            new_by_sid[inst.security_id] = inst

            if inst.is_future and inst.underlying:
                ukey = (inst.underlying.upper(), inst.exchange)
                new_by_underlying.setdefault(ukey, []).append(inst)

        with self._lock:
            self._by_symbol = new_by_symbol
            self._by_security_id = new_by_sid
            self._by_underlying = new_by_underlying
            self._loaded = True

        logger.info("instrument cache loaded: total=%d skipped=%d", len(new_by_sid), skipped)

    # ── internals ──

    def _find(self, symbol: str, exch: Exchange) -> Optional[Instrument]:
        clean = symbol.strip().upper()
        inst = self._by_symbol.get((clean, exch))
        if inst is not None:
            return inst
        stripped = clean.replace(" ", "").replace("-", "").replace("_", "")
        return self._by_symbol.get((stripped, exch))

    @staticmethod
    def _normalise_exchange(exchange: str) -> Exchange:
        up = exchange.strip().upper()
        try:
            return Exchange(up)
        except ValueError:
            mapped = SEGMENT_TO_EXCHANGE.get(up)
            if mapped is None:
                raise InstrumentNotFoundError(f"Unknown exchange: {exchange!r}")
            return Exchange(mapped)

    @staticmethod
    def _row_to_instrument(row: dict) -> Optional[Instrument]:
        symbol = (row.get("SEM_TRADING_SYMBOL") or "").strip()
        security_id = str(row.get("SEM_SMST_SECURITY_ID") or "").strip()
        if not symbol or not security_id:
            return None

        segment = (row.get("SEM_EXM_EXCH_ID") or "").strip().upper()
        exch_str = SEGMENT_TO_EXCHANGE.get(segment)
        if exch_str is None:
            return None
        exchange = Exchange(exch_str)

        name = (row.get("SEM_INSTRUMENT_NAME") or "").strip().upper()
        itype = _NAME_TO_TYPE.get(name)
        if itype is None:
            return None

        lot_size = _safe_int(row.get("SEM_LOT_UNITS"), default=1)
        tick_size = _safe_decimal(row.get("SEM_TICK_SIZE"), default="0.05")

        option_type: Optional[OptionType] = None
        strike_price = None
        expiry = None
        underlying = None
        canonical = (row.get("SEM_CUSTOM_SYMBOL") or "").strip() or None

        if itype == InstrumentType.OPTION:
            opt_raw = (row.get("SEM_OPTION_TYPE") or "").strip().upper()
            option_type = _DHAN_OPTION_TYPE.get(opt_raw)
            strike_price = _safe_decimal(row.get("SEM_STRIKE_PRICE")) if row.get("SEM_STRIKE_PRICE") is not None else None
            expiry = row.get("SEM_EXPIRY_DATE")
            if canonical:
                underlying = canonical.split()[0].upper()
            elif "-" in symbol:
                underlying = symbol.split("-", 1)[0].upper()
        elif itype == InstrumentType.FUTURE:
            expiry = row.get("SEM_EXPIRY_DATE")
            if canonical:
                underlying = canonical.split()[0].upper()
            elif "-" in symbol:
                underlying = symbol.split("-", 1)[0].upper()
            else:
                import re
                m = re.match(r"^([A-Z]+)\d+[A-Z]{3}FUT$", symbol.upper())
                underlying = (m.group(1) if m else symbol).upper()

        return Instrument(
            symbol=symbol,
            exchange=exchange,
            security_id=security_id,
            instrument_type=itype,
            lot_size=lot_size,
            tick_size=tick_size,
            name=name,
            option_type=option_type,
            strike_price=strike_price,
            expiry=expiry,
            underlying=underlying,
            canonical_symbol=canonical,
        )


def _safe_int(value, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _safe_decimal(value, default: str = "0"):
    from decimal import Decimal
    if value is None:
        return Decimal(default)
    try:
        return Decimal(str(value))
    except Exception:
        return Decimal(default)
