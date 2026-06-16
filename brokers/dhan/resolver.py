"""O(1) symbol → Instrument resolver backed by dictionaries."""

from __future__ import annotations

import logging
import threading
from collections.abc import Iterable

from brokers.dhan.domain import Exchange, Instrument, InstrumentType, OptionType
from brokers.dhan.exceptions import InstrumentNotFoundError
from brokers.dhan.segments import SEGMENT_TO_EXCHANGE

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

    def get_by_symbol(self, symbol: str, exchange: str) -> Instrument | None:
        try:
            return self._find(symbol, self._normalise_exchange(exchange))
        except Exception:
            return None

    def get_by_security_id(self, security_id: str) -> Instrument | None:
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

            # Generate robust alternate keys
            alt_keys = _generate_alternate_keys(
                symbol=inst.symbol,
                inst_type=inst.instrument_type,
                expiry=inst.expiry,
                strike=inst.strike_price,
                option_type=inst.option_type,
                underlying=inst.underlying,
                canonical_symbol=inst.canonical_symbol,
                sm_symbol_name=inst.sm_symbol_name,
            )

            # Register all alternate keys
            for k in alt_keys:
                new_by_symbol[(k, inst.exchange)] = inst

            new_by_sid[inst.security_id] = inst

            # Index by underlying for futures
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

    def _find(self, symbol: str, exch: Exchange) -> Instrument | None:
        clean = symbol.strip().upper()

        # 1. Try direct lookup
        inst = self._by_symbol.get((clean, exch))
        if inst is not None:
            return inst

        # 2. Try stripped lookup
        stripped = clean.replace(" ", "").replace("-", "").replace("_", "")
        inst = self._by_symbol.get((stripped, exch))
        if inst is not None:
            return inst

        # 3. Try standardizing Option format CALL -> CE, PUT -> PE
        if clean.endswith("CALL"):
            clean = clean[:-4] + "CE"
        elif clean.endswith("PUT"):
            clean = clean[:-3] + "PE"

        inst = self._by_symbol.get((clean, exch))
        if inst is not None:
            return inst

        # 4. Try stripped Option format standard
        stripped_cepe = clean.replace(" ", "").replace("-", "").replace("_", "")
        return self._by_symbol.get((stripped_cepe, exch))

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
    def _row_to_instrument(row: dict) -> Instrument | None:
        symbol = (row.get("SEM_TRADING_SYMBOL") or "").strip()
        security_id = str(row.get("SEM_SMST_SECURITY_ID") or "").strip()
        if not symbol or not security_id:
            return None
        try:
            if int(float(security_id)) <= 0:
                return None
        except (TypeError, ValueError):
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

        option_type: OptionType | None = None
        strike_price = None
        expiry = None
        underlying = None
        canonical = (row.get("SEM_CUSTOM_SYMBOL") or "").strip() or None

        # SM_SYMBOL_NAME is the authoritative underlying name from Dhan CSV
        sm_symbol_name = (row.get("SM_SYMBOL_NAME") or "").strip() or None

        if itype in (InstrumentType.OPTION, InstrumentType.FUTURE):
            expiry = row.get("SEM_EXPIRY_DATE")
            if itype == InstrumentType.OPTION:
                opt_raw = (row.get("SEM_OPTION_TYPE") or "").strip().upper()
                option_type = _DHAN_OPTION_TYPE.get(opt_raw)
                strike_price = _safe_decimal(row.get("SEM_STRIKE_PRICE")) if row.get("SEM_STRIKE_PRICE") is not None else None

            # Prefer SM_SYMBOL_NAME for underlying (root cause fix)
            if sm_symbol_name:
                underlying = sm_symbol_name.split()[0].upper()
            elif canonical:
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
            sm_symbol_name=sm_symbol_name,
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


def _generate_alternate_keys(
    symbol: str,
    inst_type: str | InstrumentType,
    expiry: str | None,
    strike,
    option_type,
    underlying: str | None,
    canonical_symbol: str | None,
    sm_symbol_name: str | None = None,
) -> list[str]:
    keys = []

    # 1. Primary symbol (SEM_TRADING_SYMBOL)
    sym_up = symbol.strip().upper()
    keys.append(sym_up)

    # 2. Canonical symbol (SEM_CUSTOM_SYMBOL)
    if canonical_symbol:
        canon_up = canonical_symbol.strip().upper()
        keys.append(canon_up)
        # Also generate CE/PE variant when SEM_CUSTOM_SYMBOL has CALL/PUT
        if canon_up.endswith(" CALL"):
            keys.append(canon_up[:-5] + " CE")
        elif canon_up.endswith(" PUT"):
            keys.append(canon_up[:-4] + " PE")

    # 3. Stripped symbol (no spaces, dashes, underscores)
    stripped = sym_up.replace(" ", "").replace("-", "").replace("_", "")
    keys.append(stripped)

    # 4. SM_SYMBOL_NAME as bare lookup key (e.g. "CRUDEOIL", "GOLDM", "USDINR")
    #    This is the root cause fix — enables resolution by underlying name.
    if sm_symbol_name:
        keys.append(sm_symbol_name.strip().upper())

    # Standardize option type and instrument type
    type_str = str(inst_type).upper()
    is_option = "OPT" in type_str or "OPTION" in type_str
    is_future = "FUT" in type_str or "FUTURE" in type_str

    if (is_option or is_future) and expiry and underlying:
        try:
            from datetime import datetime
            dt = datetime.strptime(expiry[:10], "%Y-%m-%d")
            dd = dt.strftime("%d")
            dd_strip = str(int(dd))
            MMM = dt.strftime("%b").upper()
            yy = dt.strftime("%y")
            yyyy = dt.strftime("%Y")

            # Month character for weekly options (1-9, O, N, D)
            month_chars = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "O", "N", "D"]
            month_char = month_chars[dt.month - 1]

            und_up = underlying.strip().upper()

            if is_option:
                opt_str = str(option_type).upper()
                ce_pe = "CE" if "CALL" in opt_str or "CE" in opt_str or "C" in opt_str else "PE"
                call_put = "CALL" if ce_pe == "CE" else "PUT"

                # Format strike price
                strike_str = ""
                if strike is not None:
                    try:
                        st_val = float(strike)
                        strike_str = str(int(st_val)) if st_val % 1 == 0 else str(st_val)
                    except (ValueError, TypeError):
                        strike_str = str(strike)

                # Generate spaced option forms with CE/PE:
                keys.append(f"{und_up} {dd} {MMM} {yy} {strike_str} {ce_pe}")
                keys.append(f"{und_up} {dd_strip} {MMM} {yy} {strike_str} {ce_pe}")
                keys.append(f"{und_up} {dd} {MMM} {yyyy} {strike_str} {ce_pe}")
                keys.append(f"{und_up} {dd_strip} {MMM} {yyyy} {strike_str} {ce_pe}")
                keys.append(f"{und_up} {dd} {MMM} {strike_str} {ce_pe}")
                keys.append(f"{und_up} {dd_strip} {MMM} {strike_str} {ce_pe}")

                # Generate spaced option forms with CALL/PUT:
                keys.append(f"{und_up} {dd} {MMM} {strike_str} {call_put}")
                keys.append(f"{und_up} {dd_strip} {MMM} {strike_str} {call_put}")

                # Generate compact option forms:
                keys.append(f"{und_up}{dd}{MMM}{yy}{strike_str}{ce_pe}")
                keys.append(f"{und_up}{dd_strip}{MMM}{yy}{strike_str}{ce_pe}")
                keys.append(f"{und_up}{dd}{MMM}{yyyy}{strike_str}{ce_pe}")
                keys.append(f"{und_up}{dd_strip}{MMM}{yyyy}{strike_str}{ce_pe}")
                keys.append(f"{und_up}{dd}{MMM}{strike_str}{ce_pe}")
                keys.append(f"{und_up}{dd_strip}{MMM}{strike_str}{ce_pe}")

                # Weekly format: e.g. NIFTY2662525000CE
                keys.append(f"{und_up}{yy}{month_char}{dd}{strike_str}{ce_pe}")
                keys.append(f"{und_up}{yy}{month_char}{dd_strip}{strike_str}{ce_pe}")

            elif is_future:
                keys.append(f"{und_up} {MMM} FUT")
                keys.append(f"{und_up} {yy} {MMM} FUT")
                keys.append(f"{und_up} {yyyy} {MMM} FUT")
                keys.append(f"{und_up} {dd} {MMM} FUT")
                keys.append(f"{und_up} FUT")

                keys.append(f"{und_up}{MMM}FUT")
                keys.append(f"{und_up}{yy}{MMM}FUT")
                keys.append(f"{und_up}{yyyy}{MMM}FUT")
                keys.append(f"{und_up}{dd}{MMM}FUT")
                keys.append(f"{und_up}FUT")
        except Exception as exc:
            logger.debug("alternate_key_generation_failed: %s", exc)

    res = []
    seen = set()
    for k in keys:
        k_clean = k.strip().upper()
        if k_clean and k_clean not in seen:
            seen.add(k_clean)
            res.append(k_clean)
    return res
