"""Options-specific Upstox domain mappers.

Extracted from ``domain_mapper.py`` (Task 2).  Contains methods for
option contract mapping and per-leg field extractors for the Upstox
option-chain payload format.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from domain import OptionContract

if TYPE_CHECKING:
    from domain.options.greeks import Greeks

from ._base import instrument_type_from_wire, to_int
from .price_parser import UpstoxPriceParser


def _leg_market_data(leg: dict) -> dict:
    if not isinstance(leg, dict):
        return {}
    md = leg.get("market_data")
    return md if isinstance(md, dict) else {}


def _leg_greeks(leg: dict) -> dict:
    if not isinstance(leg, dict):
        return {}
    g = leg.get("option_greeks")
    return g if isinstance(g, dict) else {}


def _leg_ltp(leg: dict):
    md = _leg_market_data(leg)
    val = md.get("ltp")
    return UpstoxPriceParser.parse(val) if val is not None else None


def _leg_oi(leg: dict) -> int | None:
    md = _leg_market_data(leg)
    val = md.get("oi")
    return to_int(val) if val is not None else None


def _leg_volume(leg: dict) -> int | None:
    md = _leg_market_data(leg)
    val = md.get("volume")
    return to_int(val) if val is not None else None


def _leg_iv(leg: dict):
    md = _leg_market_data(leg)
    val = md.get("iv")
    return UpstoxPriceParser.parse(val) if val is not None else None


def leg_instrument_key(leg: dict) -> str | None:
    if not isinstance(leg, dict):
        return None
    key = leg.get("instrument_key") or leg.get("instrument_token")
    return str(key) if key else None


def leg_trading_symbol(leg: dict) -> str | None:
    if not isinstance(leg, dict):
        return None
    ts = leg.get("trading_symbol") or leg.get("symbol")
    return str(ts) if ts else None


def to_option_greeks(payload: dict | None) -> Greeks:
    """Map a V3 REST option-greek object to the domain ``Greeks`` value object.

    The V3 ``/market-quote/option-greek`` response is a flat object per
    instrument key (delta/gamma/vega/theta/iv/pop) — distinct from the
    websocket ``OptionGreeks`` proto (adds ``rho``) and from the
    option-chain ``option_greeks`` leg shape (adds ``pop``). ``Greeks``
    carries the five core greeks; ``iv``/``pop`` are intentionally ignored
    here (they are surfaced on the chain leg / quote paths, not on greeks).
    """
    from domain.options.greeks import Greeks

    return Greeks.from_dict(payload)


def to_option_contract(payload: Any) -> OptionContract:
    if not isinstance(payload, dict):
        return OptionContract()
    call = payload.get("call_options") if isinstance(payload.get("call_options"), dict) else {}
    put = payload.get("put_options") if isinstance(payload.get("put_options"), dict) else {}

    return OptionContract(
        strike=UpstoxPriceParser.parse(payload.get("strike_price") or 0),
        expiry=str(payload.get("expiry") or ""),
        instrument_type=instrument_type_from_wire(
            str(payload.get("instrument_type") or "")
        ).value,
        exchange=str(payload.get("exchange") or "NFO"),
        lot_size=to_int(payload.get("lot_size")),
        call_ltp=_leg_ltp(call),
        call_oi=_leg_oi(call),
        call_volume=_leg_volume(call),
        call_iv=_leg_iv(call),
        put_ltp=_leg_ltp(put),
        put_oi=_leg_oi(put),
        put_volume=_leg_volume(put),
        put_iv=_leg_iv(put),
    )
