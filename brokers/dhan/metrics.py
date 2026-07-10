"""Backward-compat shim — metrics now live in ``brokers.dhan.resilience.metrics``."""
from brokers.dhan.resilience.metrics import (  # noqa: F401
    dhan_errors_total,
    dhan_rate_limit_retries_total,
    dhan_request_duration_seconds,
    dhan_request_total,
    dhan_ws_callbacks,
    dhan_ws_dropped_ticks_total,
    dhan_ws_reconnect_total,
    dhan_ws_subscriptions,
    dhan_ws_ticks_total,
)
