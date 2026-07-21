"""Equity-specific Upstox domain mappers.

Extracted from ``domain_mapper.py`` (Task 2).  Contains all methods
related to equity/cash-market domain mapping: holdings, positions,
trades, fund limits, and quote mappings.
"""

from __future__ import annotations

from typing import Any

from domain.entities import (
    FundLimits,
    Holding,
    Position,
    Quote,
    Trade,
)
from domain.enums import Side

from ._base import (
    exchange_from_wire,
    parse_iso,
    product_from_wire,
    to_int,
    txn_from_wire,
)
from .price_parser import UpstoxPriceParser


def _quote_from_instrument_dict(
    data: dict[str, Any],
    *,
    map_key: str = "",
) -> Quote:
    """Map a single instrument dict (v2 full or v3 LTP/OHLC envelope) to Quote."""
    ohlc = data.get("ohlc") or {}
    if not ohlc and isinstance(data.get("live_ohlc"), dict):
        ohlc = data["live_ohlc"]
    depth = data.get("depth") or {}
    bid = depth.get("buy") if isinstance(depth, dict) else None
    ask = depth.get("sell") if isinstance(depth, dict) else None

    symbol = str(data.get("symbol") or data.get("trading_symbol") or "")
    if not symbol and map_key:
        symbol = map_key.split(":")[-1] if ":" in map_key else map_key.split("|")[-1]

    close = ohlc.get("close")
    if close is None or close == "" or close == 0:
        close = data.get("cp") or ohlc.get("close") or 0

    change = data.get("change")
    if change is None or change == "":
        change = data.get("net_change") or 0

    return Quote(
        symbol=symbol,
        ltp=UpstoxPriceParser.parse(data.get("last_price") or data.get("ltp") or 0),
        open=UpstoxPriceParser.parse(ohlc.get("open") or 0),
        high=UpstoxPriceParser.parse(ohlc.get("high") or 0),
        low=UpstoxPriceParser.parse(ohlc.get("low") or 0),
        close=UpstoxPriceParser.parse(close or 0),
        volume=to_int(data.get("volume") or ohlc.get("volume")),
        oi=to_int(data.get("oi") or 0),
        bid=UpstoxPriceParser.parse(bid[0].get("price")) if isinstance(bid, list) and bid else None,
        ask=UpstoxPriceParser.parse(ask[0].get("price")) if isinstance(ask, list) and ask else None,
        change=UpstoxPriceParser.parse(change or 0),
        timestamp=parse_iso(data.get("timestamp") or data.get("last_trade_time")),
    )


def to_quote(payload: Any) -> Quote:
    """Map a single-instrument (or first of multi) market-quote payload to Quote."""
    if not isinstance(payload, dict):
        return Quote(symbol="")
    data = payload.get("data") if "data" in payload else payload
    if not isinstance(data, dict):
        data = {}
    if data and "symbol" not in data and "last_price" not in data and "ltp" not in data:
        for map_key, value in data.items():
            if isinstance(value, dict) and (
                "last_price" in value
                or "ltp" in value
                or "symbol" in value
                or "live_ohlc" in value
                or "instrument_token" in value
            ):
                return _quote_from_instrument_dict(value, map_key=str(map_key))
    return _quote_from_instrument_dict(data)


def to_quotes(payload: Any) -> dict[str, Quote]:
    """Map multi-instrument market-quote response to Quote dict."""
    out: dict[str, Quote] = {}
    if not isinstance(payload, dict):
        return out
    data = payload.get("data") if "data" in payload else payload
    if not isinstance(data, dict):
        return out
    if "last_price" in data or "ltp" in data:
        q = _quote_from_instrument_dict(data)
        if q.symbol:
            out[q.symbol] = q
        return out
    for map_key, value in data.items():
        if not isinstance(value, dict):
            continue
        if not (
            "last_price" in value
            or "ltp" in value
            or "symbol" in value
            or "live_ohlc" in value
            or "instrument_token" in value
        ):
            continue
        q = _quote_from_instrument_dict(value, map_key=str(map_key))
        if q.symbol:
            out[q.symbol] = q
    return out


def to_position(payload: Any) -> Position:
    if not isinstance(payload, dict):
        return Position(symbol="")
    return Position(
        symbol=str(payload.get("trading_symbol") or payload.get("symbol") or ""),
        exchange=exchange_from_wire(str(payload.get("exchange") or "")),
        quantity=to_int(payload.get("net_quantity") or payload.get("quantity")),
        avg_price=UpstoxPriceParser.parse(payload.get("buy_average_price") or 0),
        ltp=UpstoxPriceParser.parse(payload.get("last_price") or 0),
        unrealized_pnl=UpstoxPriceParser.parse(payload.get("unrealised") or 0),
        realized_pnl=UpstoxPriceParser.parse(payload.get("realised") or 0),
        product_type=product_from_wire(str(payload.get("product") or "I")),
    )


def to_holding(payload: Any) -> Holding:
    if not isinstance(payload, dict):
        return Holding(symbol="")
    return Holding(
        symbol=str(payload.get("trading_symbol") or payload.get("symbol") or ""),
        exchange=exchange_from_wire(str(payload.get("exchange") or "")),
        quantity=to_int(payload.get("quantity")),
        available_quantity=to_int(payload.get("quantity")),
        avg_price=UpstoxPriceParser.parse(payload.get("average_price") or 0),
        ltp=UpstoxPriceParser.parse(payload.get("last_price") or 0),
        pnl=UpstoxPriceParser.parse(payload.get("pnl") or 0),
    )


def to_trade(payload: Any) -> Trade:
    if not isinstance(payload, dict):
        return Trade(trade_id="", order_id="", symbol="", exchange="", side=Side.BUY, quantity=0)
    return Trade(
        trade_id=str(payload.get("trade_id") or ""),
        order_id=str(payload.get("order_id") or ""),
        symbol=str(payload.get("trading_symbol") or payload.get("symbol") or ""),
        exchange=exchange_from_wire(str(payload.get("exchange") or "")),
        side=txn_from_wire(str(payload.get("transaction_type") or "BUY")),
        quantity=to_int(payload.get("quantity") or payload.get("traded_quantity")),
        price=UpstoxPriceParser.parse(payload.get("price") or payload.get("average_price") or 0),
        trade_value=UpstoxPriceParser.parse(
            (payload.get("price") or 0) * (payload.get("quantity") or 0)
        ),
        timestamp=parse_iso(payload.get("trade_time") or payload.get("timestamp")),
        product_type=product_from_wire(str(payload.get("product") or "I")),
    )


def _v3_fund_totals(data: dict) -> tuple[float, float, float] | None:
    """Parse v3 funds payload; return (available, used, total) or None."""
    avail = data.get("available_to_trade")
    if not isinstance(avail, dict) or "total" not in avail:
        return None
    available = float(avail.get("total") or 0)
    cash = avail.get("cash_available_to_trade") or {}
    pledge = avail.get("pledge_available_to_trade") or {}
    cash_used = float((cash.get("margin_used") or {}).get("total") or 0)
    pledge_used = float((pledge.get("margin_used") or {}).get("total") or 0)
    used = cash_used + pledge_used
    return available, used, available + used


def to_fund_limits(payload: Any) -> FundLimits:
    if not isinstance(payload, dict):
        return FundLimits()
    data = payload.get("data") if "data" in payload else payload
    if not isinstance(data, dict):
        return FundLimits()
    v3 = _v3_fund_totals(data)
    if v3 is not None:
        available, used, total = v3
        return FundLimits(
            available_balance=UpstoxPriceParser.parse(available),
            used_margin=UpstoxPriceParser.parse(used),
            total_margin=UpstoxPriceParser.parse(total),
        )
    equity = data.get("equity") or {}
    return FundLimits(
        available_balance=UpstoxPriceParser.parse(
            equity.get("available_margin") or data.get("available_margin") or 0
        ),
        used_margin=UpstoxPriceParser.parse(
            equity.get("used_margin") or data.get("used_margin") or 0
        ),
        total_margin=UpstoxPriceParser.parse(
            equity.get("net_margin") or data.get("net_margin") or 0
        ),
    )
