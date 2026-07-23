"""Dhan native fields <-> canonical InstrumentId — pure functions, no I/O.

Ported from legacy ``src/brokers/providers/dhan/market_data/instrument_adapter.py``
(proven design). This is the **only** place Dhan's native trading-symbol/expiry
shapes should be translated to/from the canonical ``InstrumentId`` — instrument
loaders and Wire call these instead of hand-building f-strings, so both brokers
converge on the same canonical shape for the same real-world contract.
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
    """Convert parsed Dhan instrument-master fields to a canonical InstrumentId.

    ``underlying`` (e.g. from Dhan's ``SM_SYMBOL_NAME`` column) is the F&O
    root symbol and only applies to futures/options — it's a descriptive
    issuer/company name for equity rows (e.g. "TATA CONSULTANCY SERV LT" for
    TCS), never the trading symbol, so equity/index always canonicalize on
    ``symbol`` regardless of what ``underlying`` was passed.
    """
    if instrument_type == InstrumentType.OPTION and expiry and strike is not None and option_type:
        right = "CE" if option_type == OptionType.CALL else "PE"
        return InstrumentId.option(exchange, underlying or symbol, expiry, strike, right)
    if instrument_type == InstrumentType.FUTURE and expiry:
        return InstrumentId.future(exchange, underlying or symbol, expiry)
    if instrument_type == InstrumentType.INDEX:
        return InstrumentId.index(exchange, symbol)
    return InstrumentId.equity(exchange, symbol)


def to_dhan_symbol(iid: InstrumentId) -> str:
    """Build the Dhan-native trading-symbol string for *iid*.

    Examples::

        to_dhan_symbol(InstrumentId.future("MCX", "CRUDEOIL", date(2026, 7, 20)))
            -> "CRUDEOIL-20Jul2026-FUT"
        to_dhan_symbol(InstrumentId.option("MCX", "CRUDEOIL", date(2026, 7, 16), 7650, "CE"))
            -> "CRUDEOIL-16Jul2026-7650-CE"
    """
    if not iid.expiry or not iid.right:
        return iid.underlying
    expiry_str = iid.expiry.strftime("%d%b%Y")
    if iid.right == "FUT":
        return f"{iid.underlying}-{expiry_str}-FUT"
    strike_str = str(int(iid.strike)) if iid.strike == iid.strike.to_integral_value() else str(iid.strike)
    return f"{iid.underlying}-{expiry_str}-{strike_str}-{iid.right}"


def from_instrument_id(iid: InstrumentId) -> dict:
    """Canonical InstrumentId -> Dhan order/history API parameter dict."""
    result: dict = {"symbol": iid.underlying, "exchange": iid.exchange}
    if iid.expiry:
        result["expiry"] = iid.expiry.strftime("%d%b%Y")
    if iid.strike is not None:
        result["strike_price"] = str(iid.strike)
    if iid.right:
        if iid.right in ("CE", "PE"):
            result["right"] = iid.right
        elif iid.right == "FUT":
            result["instrument_type"] = "FUT"
    return result
