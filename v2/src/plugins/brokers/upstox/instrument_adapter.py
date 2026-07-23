"""Upstox native fields <-> canonical InstrumentId — pure functions, no I/O.

Ported from legacy ``src/brokers/providers/upstox/instrument_adapter.py``
(proven design). This is the **only** place Upstox's native trading-symbol/
expiry shapes should be translated to/from the canonical ``InstrumentId`` —
instrument loaders and Wire call these instead of hand-building f-strings, so
both brokers converge on the same canonical shape for the same real-world
contract.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from domain.enums import InstrumentType, OptionType
from domain.value_objects import InstrumentId


def to_instrument_id(
    *,
    symbol: str,
    exchange: str,
    instrument_type: InstrumentType,
    underlying: str | None = None,
    expiry: date | None = None,
    strike: Decimal | None = None,
    option_type: OptionType | None = None,
) -> InstrumentId:
    """Convert parsed Upstox instrument-master fields to a canonical InstrumentId.

    ``underlying`` is the F&O root symbol and only applies to futures/options —
    equity/index always canonicalize on ``symbol`` regardless of what
    ``underlying`` was passed (a descriptive/issuer name for equity rows would
    otherwise silently become the canonical symbol).
    """
    if instrument_type == InstrumentType.OPTION and expiry and strike is not None and option_type:
        right = "CE" if option_type == OptionType.CALL else "PE"
        return InstrumentId.option(exchange, underlying or symbol, expiry, strike, right)
    if instrument_type == InstrumentType.FUTURE and expiry:
        return InstrumentId.future(exchange, underlying or symbol, expiry)
    if instrument_type == InstrumentType.INDEX:
        return InstrumentId.index(exchange, symbol)
    return InstrumentId.equity(exchange, symbol)


def to_upstox_symbol(iid: InstrumentId) -> str:
    """Build the Upstox-native trading-symbol string for *iid*.

    Upstox's contract trading_symbol format is "UNDERLYING FUT DD MON YY" for
    futures and "UNDERLYING STRIKE CE|PE DD MON YY" for options (strike and
    right *before* the date). Examples::

        to_upstox_symbol(InstrumentId.future("MCX", "CRUDEOIL", date(2026, 7, 20)))
            -> "CRUDEOIL FUT 20 JUL 26"
        to_upstox_symbol(InstrumentId.option("MCX", "CRUDEOIL", date(2026, 7, 16), 7800, "PE"))
            -> "CRUDEOIL 7800 PE 16 JUL 26"
    """
    if not iid.expiry or not iid.right:
        return iid.underlying
    expiry_str = iid.expiry.strftime("%d %b %y").upper()
    if iid.right == "FUT":
        return f"{iid.underlying} FUT {expiry_str}"
    strike_str = str(int(iid.strike)) if iid.strike == iid.strike.to_integral_value() else str(iid.strike)
    return f"{iid.underlying} {strike_str} {iid.right} {expiry_str}"


_EXCH_TO_SEGMENT = {"NSE": "NSE_EQ", "BSE": "BSE_EQ", "NFO": "NSE_FO", "BFO": "BSE_FO", "MCX": "MCX_FUT"}


def from_instrument_id(iid: InstrumentId) -> dict:
    """Canonical InstrumentId -> Upstox order/history API parameter dict."""
    result: dict = {"symbol": iid.underlying, "exchange_segment": _EXCH_TO_SEGMENT.get(iid.exchange, "NSE_EQ")}
    if iid.expiry:
        result["expiry"] = iid.expiry.strftime("%Y-%m-%d")
    if iid.strike is not None:
        result["strike"] = float(iid.strike)
    if iid.right:
        if iid.right in ("CE", "PE"):
            result["option_type"] = iid.right
        elif iid.right == "FUT":
            result["instrument_type"] = "FUT"
    return result
