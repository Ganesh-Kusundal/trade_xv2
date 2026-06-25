"""Upstox Prometheus metrics — parity with Dhan observability.

Provides counters, histograms, and gauges for:
- HTTP API request duration and count
- WebSocket message throughput
- Connection status
- Order execution metrics

Usage::

    from brokers.upstox.metrics import upstox_request_duration, upstox_request_count

    # In HTTP client:
    with upstox_request_duration.labels(endpoint='orders', status=200).time():
        response = requests.post(url)
    upstox_request_count.labels(endpoint='orders', status=200).inc()
"""

from prometheus_client import Counter, Gauge, Histogram

# HTTP API metrics
upstox_request_duration = Histogram(
    "upstox_request_duration_seconds",
    "Upstox API request duration",
    ["endpoint", "status"],
    buckets=[0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
)

upstox_request_count = Counter(
    "upstox_request_total",
    "Upstox API request count",
    ["endpoint", "status"],
)

upstox_request_errors = Counter(
    "upstox_request_errors_total",
    "Upstox API error count",
    ["endpoint", "error_type"],
)

# WebSocket metrics
upstox_ws_messages = Counter(
    "upstox_websocket_messages_total",
    "Upstox WebSocket message count",
    ["type"],  # 'market_data', 'order_update', 'heartbeat'
)

upstox_ws_connected = Gauge(
    "upstox_websocket_connected",
    "Upstox WebSocket connection status (1=connected, 0=disconnected)",
)

upstox_ws_reconnects = Counter(
    "upstox_websocket_reconnects_total",
    "Upstox WebSocket reconnection count",
)

# Order metrics
upstox_order_count = Counter(
    "upstox_orders_total",
    "Upstox order count",
    ["status", "type"],  # status: 'placed', 'filled', 'cancelled'; type: 'limit', 'market', etc.
)

upstox_order_duration = Histogram(
    "upstox_order_duration_seconds",
    "Time from order placement to fill",
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0],
)

# Portfolio metrics
upstox_portfolio_value = Gauge(
    "upstox_portfolio_value",
    "Current portfolio value",
)

upstox_pnl = Gauge(
    "upstox_pnl",
    "Current realized + unrealized P&L",
)

# Token refresh metrics
upstox_token_refresh_count = Counter(
    "upstox_token_refresh_total",
    "Token refresh attempt count",
)

upstox_token_refresh_errors = Counter(
    "upstox_token_refresh_errors_total",
    "Token refresh error count",
)
