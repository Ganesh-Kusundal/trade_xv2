"""Upstox integration test fixtures.

Provides reusable fixtures for Upstox gateway integration tests:
- Mock broker with all adapters properly configured
- Mock WebSocket for stream testing
- Mock HTTP responses for order/portfolio/market data
- Thread-safe test utilities
"""

from __future__ import annotations

import threading
import time
from decimal import Decimal
from typing import Any
from unittest.mock import MagicMock, patch

import pytest


# ─── Mock WebSocket ───────────────────────────────────────────────────────

class MockWebsocket:
    """Thread-safe mock WebSocket for stream testing."""

    def __init__(self, connected: bool = False) -> None:
        self._connected = connected
        self._listeners: list[Any] = []
        self._subscriptions: list[tuple[list[str], str]] = []
        self._unsubscriptions: list[list[str]] = []
        self._connect_called = False
        self._lock = threading.Lock()

    @property
    def is_connected(self) -> bool:
        return self._connected

    def subscribe(self, keys: list[str], mode: str) -> None:
        with self._lock:
            self._subscriptions.append((keys, mode))

    def unsubscribe(self, keys: list[str]) -> None:
        with self._lock:
            self._unsubscriptions.append(keys)

    def add_listener(self, listener: Any) -> None:
        with self._lock:
            self._listeners.append(listener)

    def remove_listener(self, listener: Any) -> None:
        with self._lock:
            if listener in self._listeners:
                self._listeners.remove(listener)

    async def connect(self) -> None:
        with self._lock:
            self._connect_called = True
            self._connected = True

    def simulate_tick(self, event_type: str, raw: dict[str, Any]) -> None:
        """Dispatch a tick to all registered listeners."""
        with self._lock:
            listeners = list(self._listeners)
        for listener in listeners:
            listener(event_type, raw)

    @property
    def connect_called(self) -> bool:
        return self._connect_called

    @property
    def listeners(self) -> list[Any]:
        with self._lock:
            return list(self._listeners)

    @property
    def subscribed(self) -> list[tuple[list[str], str]]:
        with self._lock:
            return list(self._subscriptions)


# ─── Mock Broker Factory ──────────────────────────────────────────────────

def make_mock_broker(
    *,
    ws_connected: bool = False,
    allow_live_orders: bool = True,
    resolver_defn: Any = None,
) -> MagicMock:
    """Create a fully mocked UpstoxBroker with all adapters configured.

    Args:
        ws_connected: Whether the WebSocket should appear connected.
        allow_live_orders: Whether live orders are allowed.
        resolver_defn: Instrument definition to return from resolver.

    Returns:
        MagicMock configured as a realistic UpstoxBroker.
    """
    ws = MockWebsocket(connected=ws_connected)
    broker = MagicMock()

    # Settings
    settings_mock = MagicMock()
    settings_mock.allow_live_orders = allow_live_orders
    settings_mock.algo_name = ""
    settings_mock.market_protection_default = -1
    broker.settings = settings_mock

    # WebSocket
    broker.market_data_websocket = ws

    # Instrument resolver
    mock_resolver = MagicMock()
    mock_resolver.resolve.return_value = resolver_defn
    mock_resolver.is_loaded.return_value = True
    mock_resolver.search.return_value = []
    broker.instrument_resolver = mock_resolver

    # Market data clients
    broker.market_data_v2 = MagicMock()
    broker.market_data_v3 = MagicMock()
    broker.historical_v2 = MagicMock()

    # Order client
    broker.order_client = MagicMock()

    # Portfolio adapter
    broker.portfolio = MagicMock()
    broker.portfolio.get_fund_limits.return_value = MagicMock()
    broker.portfolio.get_positions.return_value = []
    broker.portfolio.get_holdings.return_value = []

    # Order query adapter
    broker.order_query = MagicMock()
    broker.order_query.get_trades.return_value = []
    broker.order_query.get_order_list.return_value = []

    # Order command adapter
    broker.order_command = MagicMock()

    # Options adapter for option_chain ABC
    broker.options = MagicMock()
    broker.options.get_option_chain.return_value = []
    broker.options.get_expiries.return_value = []

    # Futures adapter (ABC future_chain contract)
    broker.futures = MagicMock()
    broker.futures.get_contracts.return_value = [
        {
            "expiry": "2025-06-26",
            "symbol": "NIFTY25JUNFUT",
            "lot_size": 25,
            "underlying": "NIFTY",
        }
    ]
    broker.futures.get_expiries.return_value = ["2025-06-26"]

    # Disconnect
    broker.disconnect = MagicMock()

    return broker


def make_instrument_defn(
    name: str = "",
    symbol: str = "",
    trading_symbol: str = "",
    instrument_key: str = "",
    exchange_segment: str = "NSE_EQ",
) -> MagicMock:
    """Create a mock instrument definition.

    Args:
        name: Full instrument name.
        symbol: Trading symbol.
        trading_symbol: Alternative trading symbol.
        instrument_key: Upstox instrument key.
        exchange_segment: Exchange segment.

    Returns:
        MagicMock configured as an instrument definition.
    """
    defn = MagicMock()
    defn.name = name
    defn.symbol = symbol
    defn.trading_symbol = trading_symbol
    defn.instrument_key = instrument_key
    defn.exchange_segment = exchange_segment
    return defn


# ─── Market Data Response Factories ───────────────────────────────────────

def make_ltp_response(symbol: str, price: float) -> dict[str, Any]:
    """Create a realistic Upstox LTP API response.

    Args:
        symbol: Trading symbol.
        price: Last traded price.

    Returns:
        Dict matching Upstox V2 LTP endpoint format.
    """
    return {
        "status": "success",
        "data": {
            f"NSE_EQ|{symbol}": {
                "instrument_key": f"NSE_EQ|{symbol}",
                "last_price": price,
            }
        }
    }


def make_quote_response(symbol: str, **kwargs: Any) -> dict[str, Any]:
    """Create a realistic Upstox Quote API response.

    Args:
        symbol: Trading symbol.
        **kwargs: OHLCV values to override defaults.

    Returns:
        Dict matching Upstox V2 Quote endpoint format.
    """
    data = {
        "instrument_key": f"NSE_EQ|{symbol}",
        "last_price": kwargs.get("last_price", 1500.0),
        "net_change": kwargs.get("net_change", 25.0),
        "volume": kwargs.get("volume", 500000),
        "ohlc": {
            "open": kwargs.get("open", 1480.0),
            "high": kwargs.get("high", 1520.0),
            "low": kwargs.get("low", 1475.0),
            "close": kwargs.get("close", 1475.0),
        },
    }
    return {
        "status": "success",
        "data": {f"NSE_EQ|{symbol}": data}
    }


def make_depth_response(symbol: str, bids: list[dict] | None = None, asks: list[dict] | None = None) -> dict[str, Any]:
    """Create a realistic Upstox Depth API response.

    Args:
        symbol: Trading symbol.
        bids: List of bid level dicts.
        asks: List of ask level dicts.

    Returns:
        Dict matching Upstox V2 Depth endpoint format.
    """
    if bids is None:
        bids = [{"price": 1500.0, "quantity": 100, "orders": 5}]
    if asks is None:
        asks = [{"price": 1501.0, "quantity": 150, "orders": 3}]

    return {
        "status": "success",
        "data": {
            f"NSE_EQ|{symbol}": {
                "depth": {"buy": bids, "sell": asks}
            }
        }
    }


def make_order_response(order_id: str, status: str = "success") -> dict[str, Any]:
    """Create a realistic Upstox order placement API response.

    Args:
        order_id: The order ID to return.
        status: Response status ("success" or error).

    Returns:
        Dict matching Upstox V3 order placement endpoint format.
    """
    return {
        "status": status,
        "data": {"order_id": order_id},
    }


def make_cancel_response(order_id: str, success: bool = True) -> dict[str, Any]:
    """Create a realistic Upstox order cancellation API response.

    Args:
        order_id: The order ID.
        success: Whether cancellation succeeded.

    Returns:
        Dict matching Upstox cancel endpoint format.
    """
    if success:
        return {
            "status": "success",
            "message": "Order cancelled",
        }
    return {
        "status": "error",
        "errors": [{"errorCode": "BRO_ERR_ORDER_NOT_FOUND", "message": "Order not found"}],
    }


def make_funds_response(**kwargs: Any) -> dict[str, Any]:
    """Create a realistic Upstox funds API response.

    Args:
        **kwargs: Fund values to override defaults.

    Returns:
        Dict matching Upstox funds endpoint format.
    """
    return {
        "status": "success",
        "data": {
            "equity": {
                "available_margin": kwargs.get("available", 100000.0),
                "used_margin": kwargs.get("used", 0.0),
                "total_margin": kwargs.get("total", 100000.0),
            }
        }
    }


def make_positions_response(positions: list[dict] | None = None) -> dict[str, Any]:
    """Create a realistic Upstox positions API response.

    Args:
        positions: List of position dicts.

    Returns:
        Dict matching Upstox positions endpoint format.
    """
    if positions is None:
        positions = []
    return {
        "status": "success",
        "data": {
            "net": positions,
            "clearing": [],
        }
    }


def make_holdings_response(holdings: list[dict] | None = None) -> dict[str, Any]:
    """Create a realistic Upstox holdings API response.

    Args:
        holdings: List of holding dicts.

    Returns:
        Dict matching Upstox holdings endpoint format.
    """
    if holdings is None:
        holdings = []
    return {
        "status": "success",
        "data": holdings,
    }


def make_tick_payload(
    instrument_key: str,
    last_price: float = 1500.0,
    close_price: float = 1475.0,
    volume: int = 5000,
    frame_type: str = "ltpc",
) -> dict[str, Any]:
    """Create a realistic Upstox WebSocket tick payload.

    Args:
        instrument_key: Upstox instrument key.
        last_price: Last traded price.
        close_price: Previous close price.
        volume: Traded volume.
        frame_type: Frame type (ltpc, full, etc.).

    Returns:
        Dict matching Upstox WebSocket tick format.
    """
    return {
        "frame_type": frame_type,
        "payload": {
            "instrument_key": instrument_key,
            "last_price": last_price,
            "close_price": close_price,
            "volume": volume,
        }
    }


# ─── Error Response Factories ─────────────────────────────────────────────

def make_auth_error() -> dict[str, Any]:
    """Create an authentication error response."""
    return {
        "status": "error",
        "errors": [
            {
                "errorCode": "BRO_ERR_UNAUTHORIZED",
                "message": "Authentication failed. Invalid or expired token.",
            }
        ],
    }


def make_rate_limit_error() -> dict[str, Any]:
    """Create a rate limit error response."""
    return {
        "status": "error",
        "errors": [
            {
                "errorCode": "BRO_ERR_RATE_LIMIT",
                "message": "Rate limit exceeded. Please retry after some time.",
            }
        ],
    }


def make_not_found_error() -> dict[str, Any]:
    """Create a not found error response."""
    return {
        "status": "error",
        "errors": [
            {
                "errorCode": "BRO_ERR_NOT_FOUND",
                "message": "Resource not found.",
            }
        ],
    }
