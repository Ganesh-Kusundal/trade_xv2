"""DhanMessageParser — pure message transformation logic.

Responsibility: Transform raw SDK message dicts into canonical quote/depth
dicts. This class has no side effects — it only reads input and returns
transformed output. Thread-safe via RLock for resolver calls.
"""

from __future__ import annotations

import logging
import threading
from decimal import Decimal
from typing import Any

logger = logging.getLogger(__name__)


class DhanMessageParser:
    """Pure message parser for Dhan WebSocket data.

    Transforms raw SDK message dicts into canonical internal format:
    - transform_quote(): SDK quote/ticker dict → canonical quote dict
    - transform_depth(): SDK depth dict → canonical depth dict
    - classify_message_type(): Message type string → canonical type enum

    Thread-safe: Uses RLock when calling the resolver to prevent
    concurrent access issues.
    """

    def __init__(self, resolver: Any | None = None) -> None:
        """Initialize parser.

        Args:
            resolver: Optional SymbolResolver for security_id → symbol lookup.
        """
        self._resolver = resolver
        self._lock = threading.RLock()

    def transform_quote(self, data: dict) -> dict:
        """Transform SDK quote/ticker data to canonical quote dict.

        Args:
            data: Raw SDK message dict with keys like security_id, last_price/LTP,
                  open, high, low, close, volume.

        Returns:
            Canonical dict with keys: symbol, security_id, ltp, open, high, low,
            close, volume, change. All price fields are Decimal or None.
        """
        security_id = str(data.get("security_id", ""))
        symbol = security_id

        if self._resolver:
            try:
                with self._lock:
                    inst = self._resolver.get_by_security_id(security_id)
                if inst:
                    symbol = inst.symbol
            except Exception as exc:
                logger.warning(
                    "dhan_ws_symbol_resolution_failed",
                    extra={"security_id": security_id, "exception_type": type(exc).__name__},
                )

        ltp_raw = data.get("last_price", data.get("LTP", "0"))

        def _to_decimal(key: str) -> Decimal | None:
            val = data.get(key)
            if val is None:
                return None
            return Decimal(str(val))

        return {
            "symbol": symbol,
            "security_id": security_id,
            "ltp": Decimal(str(ltp_raw)),
            "open": _to_decimal("open"),
            "high": _to_decimal("high"),
            "low": _to_decimal("low"),
            "close": _to_decimal("close"),
            "volume": int(data.get("volume", 0)),
            "change": Decimal("0"),
        }

    def transform_depth(self, data: dict) -> dict:
        """Transform SDK depth data to canonical depth dict.

        Args:
            data: Raw SDK message dict with keys like security_id, last_price/LTP,
                  depth (dict or list).

        Returns:
            Canonical dict with keys: symbol, security_id, ltp, depth.
        """
        security_id = str(data.get("security_id", ""))
        symbol = security_id

        if self._resolver:
            try:
                with self._lock:
                    inst = self._resolver.get_by_security_id(security_id)
                if inst:
                    symbol = inst.symbol
            except Exception as exc:
                logger.warning(
                    "dhan_ws_symbol_resolution_failed",
                    extra={"security_id": security_id, "exception_type": type(exc).__name__},
                )

        depth_data = data.get("depth", [])

        return {
            "symbol": symbol,
            "security_id": security_id,
            "ltp": Decimal(str(data.get("last_price", data.get("LTP", "0")))),
            "depth": depth_data,
        }

    def classify_message_type(self, data_type: str | None) -> str:
        """Classify message type into canonical category.

        Args:
            data_type: Raw message type string from SDK (e.g. "Quote Data",
                      "Ticker Data", "Market Depth", "Full Data").

        Returns:
            Canonical type string: "TICKER", "QUOTE", "DEPTH", "FULL", or "UNKNOWN".
        """
        if not data_type:
            return "UNKNOWN"

        type_map = {
            "Ticker Data": "TICKER",
            "Quote Data": "QUOTE",
            "Market Depth": "DEPTH",
            "Full Data": "FULL",
        }
        return type_map.get(data_type, "UNKNOWN")
