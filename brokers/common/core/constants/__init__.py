"""Constants package — re-exports all constants for backward compatibility.

This package splits the monolithic constants.py into focused sub-modules:
- timeouts: Stop timeouts, HTTP timeouts, sleep intervals
- resilience: Retry, circuit breaker, backoff configuration
- auth: Token lifecycle and authentication constants
- risk: Risk thresholds, position limits, capital defaults
- market: Market hours, exchanges, tick sizes, timezone
- observability: HTTP server configuration

All constants are re-exported here to maintain backward compatibility with
existing imports from ``brokers.common.core.constants``.
"""
from __future__ import annotations

from brokers.common.core.constants.timeouts import (
    DEFAULT_STOP_TIMEOUT_SECONDS,
    DEFAULT_HTTP_TIMEOUT_SECONDS,
    MIN_SLEEP_SECONDS,
)
from brokers.common.core.constants.resilience import (
    MAX_RETRY_DELAY_MS,
    RETRY_BASE_DELAY_MS,
    MAX_RETRY_ATTEMPTS,
    CIRCUIT_BREAKER_FAILURE_THRESHOLD,
    CIRCUIT_BREAKER_SUCCESS_THRESHOLD,
    CIRCUIT_BREAKER_OPEN_DURATION_MS,
    BACKOFF_MULTIPLIER,
    BACKOFF_JITTER,
)
from brokers.common.core.constants.auth import (
    TOKEN_REFRESH_RECOMMENDED_BUFFER_SECONDS,
    DHAN_TOKEN_REFRESH_BUFFER_SECONDS,
    DHAN_TOKEN_SCHEDULER_INTERVAL_SECONDS,
    DHAN_TOKEN_LIFETIME_SECONDS,
    DHAN_REFRESH_COOLDOWN_SECONDS,
    TOKEN_CLOCK_SKEW_SECONDS,
)
from brokers.common.core.constants.risk import (
    RISK_DAILY_LOSS_PERCENT,
    RISK_POSITION_PERCENT,
    RISK_GROSS_PERCENT,
    PHANTOM_CAPITAL_INR,
    DHAN_NOTIONAL_WARNING_INR,
)
from brokers.common.core.constants.market import (
    DEFAULT_TICK_SIZE,
    DEFAULT_EXCHANGE_SEGMENT_FALLBACK,
    DEFAULT_EXCHANGE,
    NSE_OPEN_HOUR_IST,
    NSE_OPEN_MINUTE_IST,
    NSE_CLOSE_HOUR_IST,
    NSE_CLOSE_MINUTE_IST,
    MCX_OPEN_HOUR_IST,
    MCX_OPEN_MINUTE_IST,
    MCX_CLOSE_HOUR_IST,
    MCX_CLOSE_MINUTE_IST,
    IST_OFFSET,
)
from brokers.common.core.constants.observability import (
    OBSERVABILITY_DEFAULT_HOST,
    OBSERVABILITY_DEFAULT_PORT,
)

# ── OMS / reconciliation cadence (not yet split) ──────────────────────────

#: Reconciliation cycle (seconds). Used by TradingContext, factory,
#: and ReconciliationService default.
RECONCILIATION_INTERVAL_SECONDS: float = 300.0

#: Daily-PnL reset poll interval (seconds). Used by
#: DailyPnlResetScheduler.
DAILY_PNL_POLL_INTERVAL_SECONDS: float = 60.0

#: Default rollover hour in IST (0 = midnight). Used by
#: DailyPnlResetScheduler.
DAILY_PNL_ROLLOVER_HOUR_IST: int = 0

#: Number of days the ProcessedTradeRepository retains trade IDs in
#: memory before cleanup() may evict them.
PROCESSED_TRADE_RETENTION_SECONDS: int = 24 * 60 * 60  # 86_400

#: Periodic cleanup interval for ProcessedTradeRepository.
PROCESSED_TRADE_CLEANUP_INTERVAL_SECONDS: int = 60 * 60  # 1h

# ── Batching / threading ───────────────────────────────────────────────────

#: Number of worker threads used by BatchFetchMixin.
BATCH_MAX_WORKERS: int = 5

#: Max instruments per Dhan depth-20 WebSocket subscription.
DHAN_DEPTH_20_MAX_INSTRUMENTS: int = 50

#: Max instruments per Dhan depth-200 WebSocket subscription.
DHAN_DEPTH_200_MAX_INSTRUMENTS: int = 1

# ── Idempotency ────────────────────────────────────────────────────────────

#: Dhan OrderIdempotencyCache max size.
DHAN_IDEMPOTENCY_MAX_SIZE: int = 1_000

#: Dhan OrderIdempotencyCache TTL (seconds).
DHAN_IDEMPOTENCY_TTL_SECONDS: int = 60 * 60  # 1h

# ── Dead-letter queue ──────────────────────────────────────────────────────

#: Maximum events the DeadLetterQueue will buffer before dropping the
#: oldest. Larger values consume more memory.
DEAD_LETTER_QUEUE_MAX_SIZE: int = 10_000

# ── Log / instrumentation ──────────────────────────────────────────────────

#: Default log level used by :func:`brokers.common.logging_config.setup_logging`.
DEFAULT_LOG_LEVEL: str = "INFO"

#: Default log level for noisy third-party loggers.
THIRD_PARTY_LOG_LEVEL: str = "WARNING"

# ── History defaults ───────────────────────────────────────────────────────

#: Default pagination window for historical candle downloads (days).
DEFAULT_HISTORY_PAGE_DAYS: int = 365

#: BrokerCapabilities default for max intraday history (days).
DEFAULT_MAX_INTRADAY_DAYS: int = 90

#: BrokerCapabilities default for max multi-day history (days).
DEFAULT_MAX_DAILY_DAYS: int = 365 * 10

# ── Upstox-specific ────────────────────────────────────────────────────────

#: Upstox Bearer-token refresh interval (seconds). Used by the Upstox
#: auto-reconnect. Lives here for now; will move to
#: ``brokers.upstox.auth.config`` once REF-14 lands.
UPSTOX_DEFAULT_RATE_PER_SECOND: float = 10.0

#: Upstox WebSocket ping interval (seconds).
UPSTOX_WS_PING_INTERVAL_SECONDS: int = 20

#: Upstox WebSocket ping timeout (seconds).
UPSTOX_WS_PING_TIMEOUT_SECONDS: int = 20

#: Upstox default instrument-cache validity (hours).
UPSTOX_INSTRUMENT_CACHE_HOURS: int = 24

__all__ = [
    # timeouts
    "DEFAULT_STOP_TIMEOUT_SECONDS",
    "DEFAULT_HTTP_TIMEOUT_SECONDS",
    "MIN_SLEEP_SECONDS",
    # resilience
    "MAX_RETRY_DELAY_MS",
    "RETRY_BASE_DELAY_MS",
    "MAX_RETRY_ATTEMPTS",
    "CIRCUIT_BREAKER_FAILURE_THRESHOLD",
    "CIRCUIT_BREAKER_SUCCESS_THRESHOLD",
    "CIRCUIT_BREAKER_OPEN_DURATION_MS",
    "BACKOFF_MULTIPLIER",
    "BACKOFF_JITTER",
    # auth
    "TOKEN_REFRESH_RECOMMENDED_BUFFER_SECONDS",
    "DHAN_TOKEN_REFRESH_BUFFER_SECONDS",
    "DHAN_TOKEN_SCHEDULER_INTERVAL_SECONDS",
    "DHAN_TOKEN_LIFETIME_SECONDS",
    "DHAN_REFRESH_COOLDOWN_SECONDS",
    "TOKEN_CLOCK_SKEW_SECONDS",
    # risk
    "RISK_DAILY_LOSS_PERCENT",
    "RISK_POSITION_PERCENT",
    "RISK_GROSS_PERCENT",
    "PHANTOM_CAPITAL_INR",
    "DHAN_NOTIONAL_WARNING_INR",
    # market
    "DEFAULT_TICK_SIZE",
    "DEFAULT_EXCHANGE_SEGMENT_FALLBACK",
    "DEFAULT_EXCHANGE",
    "NSE_OPEN_HOUR_IST",
    "NSE_OPEN_MINUTE_IST",
    "NSE_CLOSE_HOUR_IST",
    "NSE_CLOSE_MINUTE_IST",
    "MCX_OPEN_HOUR_IST",
    "MCX_OPEN_MINUTE_IST",
    "MCX_CLOSE_HOUR_IST",
    "MCX_CLOSE_MINUTE_IST",
    "IST_OFFSET",
    # observability
    "OBSERVABILITY_DEFAULT_HOST",
    "OBSERVABILITY_DEFAULT_PORT",
    # OMS
    "RECONCILIATION_INTERVAL_SECONDS",
    "DAILY_PNL_POLL_INTERVAL_SECONDS",
    "DAILY_PNL_ROLLOVER_HOUR_IST",
    "PROCESSED_TRADE_RETENTION_SECONDS",
    "PROCESSED_TRADE_CLEANUP_INTERVAL_SECONDS",
    # batching
    "BATCH_MAX_WORKERS",
    "DHAN_DEPTH_20_MAX_INSTRUMENTS",
    "DHAN_DEPTH_200_MAX_INSTRUMENTS",
    # idempotency
    "DHAN_IDEMPOTENCY_MAX_SIZE",
    "DHAN_IDEMPOTENCY_TTL_SECONDS",
    # DLQ
    "DEAD_LETTER_QUEUE_MAX_SIZE",
    # logging
    "DEFAULT_LOG_LEVEL",
    "THIRD_PARTY_LOG_LEVEL",
    # history
    "DEFAULT_HISTORY_PAGE_DAYS",
    "DEFAULT_MAX_INTRADAY_DAYS",
    "DEFAULT_MAX_DAILY_DAYS",
    # Upstox
    "UPSTOX_DEFAULT_RATE_PER_SECOND",
    "UPSTOX_WS_PING_INTERVAL_SECONDS",
    "UPSTOX_WS_PING_TIMEOUT_SECONDS",
    "UPSTOX_INSTRUMENT_CACHE_HOURS",
]
