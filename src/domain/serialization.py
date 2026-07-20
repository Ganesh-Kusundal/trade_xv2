"""Domain serialization adapters.

Parsing of broker-neutral domain value objects from raw ``dict`` payloads
lives here rather than inside the entities themselves — parsing belongs in
adapters, not domain entities.

Entity ``from_dict`` classmethods remain as thin delegates to the functions
in this module for backward compatibility, but new code should call these
adapter functions directly.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from domain.entities.options import (
    OptionChain,
    OptionLeg,
    OptionStrike,
)
from domain.parsing import parse_decimal as _decimal_or_none
from domain.parsing import parse_int as _parse_int_or_none


def option_leg_from_dict(data: dict | None) -> OptionLeg:
    """Parse a single CE/PE leg from a broker-neutral dict."""
    if not isinstance(data, dict):
        return OptionLeg()
    nested_greeks = data.get("greeks")
    if isinstance(nested_greeks, dict) and nested_greeks:
        greeks = dict(nested_greeks)
    else:
        flat: dict[str, Any] = {}
        for key in ("delta", "theta", "gamma", "vega", "rho"):
            val = data.get(key)
            if val is not None:
                flat[key] = val
        greeks = flat or None
    return OptionLeg(
        ltp=_decimal_or_none(data.get("ltp")),
        oi=_parse_int_or_none(data.get("oi")),
        volume=_parse_int_or_none(data.get("volume")),
        iv=_decimal_or_none(data.get("iv")),
        bid=_decimal_or_none(data.get("bid")),
        ask=_decimal_or_none(data.get("ask")),
        symbol=data.get("symbol"),
        instrument_key=data.get("instrument_key") or data.get("security_id"),
        trading_symbol=data.get("trading_symbol") or data.get("tradingSymbol"),
        greeks=greeks,
    )


def option_strike_from_dict(data: dict) -> OptionStrike:
    """Parse one strike row (call + put legs) from a dict."""
    strike_val = data.get("strike") or data.get("strikePrice")
    strike = _decimal_or_none(strike_val) or Decimal("0")
    call_raw = data.get("call") or data.get("CE") or {}
    put_raw = data.get("put") or data.get("PE") or {}
    return OptionStrike(
        strike=strike,
        call=option_leg_from_dict(call_raw if isinstance(call_raw, dict) else {}),
        put=option_leg_from_dict(put_raw if isinstance(put_raw, dict) else {}),
    )


def option_chain_from_dict(data: dict | None) -> OptionChain:
    """Parse a full option chain from a broker-neutral dict."""
    if not data:
        return OptionChain(underlying="", exchange="", expiry="")
    strikes = tuple(
        option_strike_from_dict(row) for row in data.get("strikes", []) if isinstance(row, dict)
    )
    return OptionChain(
        underlying=str(data.get("underlying", "")),
        exchange=str(data.get("exchange", "")),
        expiry=str(data.get("expiry", "")),
        strikes=strikes,
        spot=_decimal_or_none(data.get("spot")),
    )
