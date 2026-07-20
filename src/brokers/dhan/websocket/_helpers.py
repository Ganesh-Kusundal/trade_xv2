"""Shared helpers for Dhan WebSocket services.

Extracted from the former monolithic ``brokers/dhan/websocket.py`` (Task 5.1).
Contains lazy SDK loaders, instrument conversion, the ``_DhanContext`` shim,
and the ``_to_decimal`` utility — all shared by the three WebSocket service
classes (``DhanMarketFeed``, ``DhanOrderStream``, ``PollingMarketFeed``).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime
from decimal import Decimal
from typing import Any

from brokers.dhan.segments import to_sdk_int

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Lazy SDK loaders — avoid importing dhanhq at module-import time so that
# ``import brokers.dhan.wire`` works even when the SDK is not installed.
# ---------------------------------------------------------------------------


def _sdk_market_feed_class() -> type:
    """Lazy import so ``import brokers.dhan.wire`` does not require dhanhq at import time."""
    from dhanhq import marketfeed as mf

    # dhanhq >=2.x renamed MarketFeed -> DhanFeed
    return getattr(mf, "MarketFeed", mf.DhanFeed)


def _sdk_order_update_class() -> type:
    from dhanhq.orderupdate import OrderUpdate

    return OrderUpdate


# ---------------------------------------------------------------------------
# Mode map — SDK subscription-type constants (cached at module level).
# ---------------------------------------------------------------------------

# Module-level cache for the mode map (computed once, lazily on first access).
# Avoids rebuilding the dict and re-importing MarketFeed on every call.


class _ModeMapCache:
    """Lazy-cached mode-name -> SDK constant mapping (class-based state holder)."""

    _map: dict[str, int] | None = None


def _sdk_subscription_ticker() -> int:
    """SDK constant for default LTP/Ticker subscription mode."""
    from dhanhq import marketfeed as mf_mod

    mf_cls = _sdk_market_feed_class()
    return getattr(mf_cls, "Ticker", mf_mod.Ticker)


def _mode_map() -> dict[str, int]:
    """Return the mode-name -> SDK constant mapping (cached at module level)."""
    if _ModeMapCache._map is None:
        from dhanhq import marketfeed as mf_mod

        mf = _sdk_market_feed_class()

        def _sdk_const(name: str) -> int:
            return getattr(mf, name, getattr(mf_mod, name))

        _ModeMapCache._map = {
            "LTP": _sdk_const("Ticker"),
            "TICKER": _sdk_const("Ticker"),
            "QUOTE": _sdk_const("Quote"),
            "FULL": _sdk_const("Full"),
            "DEPTH": _sdk_const("Quote"),  # v2 does not support Depth (19)
        }
    return _ModeMapCache._map


# ---------------------------------------------------------------------------
# Decimal conversion helper
# ---------------------------------------------------------------------------


def _to_decimal(value: Any, default: str = "0") -> Decimal:
    """Convert a value to Decimal, avoiding redundant conversion if already Decimal.

    Task 2.4: _transform_quote already produces Decimal values. This helper
    ensures _publish_tick does not re-convert them through str() unnecessarily,
    while still handling non-Decimal inputs from the backfill path.
    """
    if isinstance(value, Decimal):
        return value
    if value is None:
        return Decimal(default)
    return Decimal(str(value))


# ---------------------------------------------------------------------------
# Market-feed payload parsing (pure, stateless)
# ---------------------------------------------------------------------------


def _resolve_security_symbol(security_id: str, resolver: Any = None) -> str:
    """Map *security_id* to a trading symbol via *resolver*, falling back to id."""
    symbol = security_id
    if not resolver:
        return symbol
    try:
        inst = resolver.get_by_security_id(security_id)
        if inst:
            symbol = inst.symbol
    except Exception as exc:
        logger.warning(
            "dhan_ws_symbol_resolution_failed",
            extra={"security_id": security_id, "exception_type": type(exc).__name__},
        )
    return symbol


def _normalize_sdk_depth(raw_depth: Any) -> dict[str, list[dict[str, Any]]]:
    """Convert Dhan SDK depth payload to {bids, asks} ladder dict."""
    if isinstance(raw_depth, dict):
        return {
            "bids": list(raw_depth.get("bids") or []),
            "asks": list(raw_depth.get("asks") or []),
        }
    if isinstance(raw_depth, list):
        bids: list[dict[str, Any]] = []
        asks: list[dict[str, Any]] = []
        for row in raw_depth:
            if not isinstance(row, dict):
                continue
            bid_qty = int(row.get("bid_quantity") or 0)
            ask_qty = int(row.get("ask_quantity") or 0)
            if bid_qty > 0:
                bids.append(
                    {
                        "price": row.get("bid_price", 0),
                        "quantity": bid_qty,
                        "orders": int(row.get("bid_orders") or 0),
                    }
                )
            if ask_qty > 0:
                asks.append(
                    {
                        "price": row.get("ask_price", 0),
                        "quantity": ask_qty,
                        "orders": int(row.get("ask_orders") or 0),
                    }
                )
        return {"bids": bids, "asks": asks}
    return {"bids": [], "asks": []}


def _best_bid_ask(raw_depth: Any) -> tuple[Decimal | None, Decimal | None]:
    """Extract best (top-of-book) bid/ask from a Full Data frame's ``depth`` list."""
    if not isinstance(raw_depth, list) or not raw_depth:
        return None, None
    top = raw_depth[0]
    if not isinstance(top, dict):
        return None, None
    bid = top.get("bid_price")
    ask = top.get("ask_price")
    return (
        Decimal(str(bid)) if bid not in (None, "") else None,
        Decimal(str(ask)) if ask not in (None, "") else None,
    )


def _parse_quote_exchange_time(data: dict, now: datetime) -> datetime:
    """Prefer exchange time from the SDK frame; fall back to *now*."""
    for key in ("last_traded_time", "exchange_timestamp", "LTT", "timestamp"):
        ts_raw = data.get(key)
        if ts_raw is None or ts_raw == "":
            continue
        if isinstance(ts_raw, datetime):
            return ts_raw if ts_raw.tzinfo else ts_raw.replace(tzinfo=now.tzinfo)
        try:
            if isinstance(ts_raw, int | float):
                if ts_raw <= 0:
                    continue
                if ts_raw > 1e11:
                    return datetime.fromtimestamp(ts_raw / 1000, tz=now.tzinfo)
                return datetime.fromtimestamp(ts_raw, tz=now.tzinfo)
            if isinstance(ts_raw, str) and ts_raw.strip():
                parsed = datetime.fromisoformat(ts_raw)
                return parsed if parsed.tzinfo else parsed.replace(tzinfo=now.tzinfo)
        except (ValueError, OSError, OverflowError):
            continue
    return now


def _transform_quote(data: dict, resolver: Any = None) -> dict:
    """Transform a raw SDK ticker/quote frame into a canonical quote dict."""
    from domain.ports.time_service import get_current_clock

    now = get_current_clock().now()
    security_id = str(data.get("security_id", ""))
    symbol = _resolve_security_symbol(security_id, resolver)
    bid, ask = _best_bid_ask(data.get("depth"))
    return {
        "symbol": symbol,
        "ltp": Decimal(str(data.get("last_price", data.get("LTP", "0")))),
        "open": Decimal(str(data["open"])) if data.get("open") else None,
        "high": Decimal(str(data["high"])) if data.get("high") else None,
        "low": Decimal(str(data["low"])) if data.get("low") else None,
        "close": Decimal(str(data["close"])) if data.get("close") else None,
        "volume": int(data.get("volume", 0)),
        "change": Decimal("0"),
        "bid": bid,
        "ask": ask,
        "timestamp": _parse_quote_exchange_time(data, now),
    }


def _transform_depth(data: dict, resolver: Any = None) -> dict:
    """Transform a raw SDK depth/full frame into a canonical depth dict."""
    security_id = str(data.get("security_id", ""))
    symbol = _resolve_security_symbol(security_id, resolver)
    return {
        "symbol": symbol,
        "ltp": Decimal(str(data.get("last_price", data.get("LTP", "0")))),
        "depth": _normalize_sdk_depth(data.get("depth", [])),
    }


# ---------------------------------------------------------------------------
# Instrument conversion
# ---------------------------------------------------------------------------


def _to_sdk_instruments(instruments: list[tuple]) -> list[tuple]:
    """Convert human-readable instruments to SDK format.

    Accepts:
        [(exchange_str, security_id_str, mode_str), ...]
        e.g. [("MCX_COMM", "466583", "LTP")]

    Returns:
        [(exchange_int, security_id_int, type_int), ...]
        e.g. [(5, 466583, 15)]
    """
    sdk_instruments = []
    # Task 1.6: resolve mode map once before the loop (was called per instrument).
    mode_map = _mode_map()
    default_mode = _sdk_subscription_ticker()
    for item in instruments:
        if len(item) != 3:
            logger.warning("Skipping malformed instrument: %s", item)
            continue
        exchange, security_id, mode = item

        # Already SDK-format — pass through but keep security_id as string
        if isinstance(exchange, int) and isinstance(mode, int):
            sid_str = str(security_id)
            sdk_instruments.append((exchange, sid_str, mode))
            continue

        # Convert strings to SDK integers
        if isinstance(exchange, int):
            exch_int = exchange
        else:
            try:
                exch_int = to_sdk_int(str(exchange))
            except ValueError:
                exch_int = None
        if exch_int is None:
            logger.warning("Unknown exchange: %s", exchange)
            continue
        sid_str = str(security_id)
        mode_int = (
            mode_map.get(str(mode).upper(), default_mode) if isinstance(mode, str) else int(mode)
        )
        sdk_instruments.append((exch_int, sid_str, mode_int))
    return sdk_instruments


# ---------------------------------------------------------------------------
# Dhan SDK context shim
# ---------------------------------------------------------------------------


class _DhanContext:
    """Shim to satisfy SDK's dhan_context interface.

    Supports both static token and token provider callable.
    """

    def __init__(
        self,
        client_id: str,
        access_token: str | None = None,
        access_token_fn: Callable[[], str] | None = None,
    ):
        self._client_id = client_id
        self._access_token = access_token or ""
        self._access_token_fn = access_token_fn

    def get_client_id(self) -> str:
        return self._client_id

    def get_access_token(self) -> str:
        if self._access_token_fn:
            try:
                return self._access_token_fn()
            except Exception as exc:
                logger.error(
                    "dhan_ws_access_token_fn_failed",
                    extra={"exception_type": type(exc).__name__, "exception_message": str(exc)},
                )
        return self._access_token

    def get_dhan_http(self):
        return None

    def update_token(self, token: str) -> None:
        """Update the static token snapshot."""
        self._access_token = token
