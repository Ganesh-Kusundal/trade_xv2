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

from domain.constants.timeouts import (
    DEFAULT_STOP_TIMEOUT_SECONDS,
    DEFAULT_HTTP_TIMEOUT_SECONDS,
    HISTORY_CACHE_TTL_SECONDS,
    MIN_SLEEP_SECONDS,
    QUOTE_CACHE_TTL_SECONDS,
)
from domain.constants.resilience import (
    MAX_RETRY_DELAY_MS,
    RETRY_BASE_DELAY_MS,
    MAX_RETRY_ATTEMPTS,
    CIRCUIT_BREAKER_FAILURE_THRESHOLD,
    CIRCUIT_BREAKER_SUCCESS_THRESHOLD,
    CIRCUIT_BREAKER_OPEN_DURATION_MS,
    BACKOFF_MULTIPLIER,
    BACKOFF_JITTER,
)
from domain.constants.auth import (
    TOKEN_REFRESH_RECOMMENDED_BUFFER_SECONDS,
    DHAN_TOKEN_REFRESH_BUFFER_SECONDS,
    DHAN_TOKEN_SCHEDULER_INTERVAL_SECONDS,
    DHAN_TOKEN_LIFETIME_SECONDS,
    DHAN_REFRESH_COOLDOWN_SECONDS,
    TOKEN_CLOCK_SKEW_SECONDS,
)
from domain.constants.risk import (
    RISK_DAILY_LOSS_PERCENT,
    RISK_POSITION_PERCENT,
    RISK_GROSS_PERCENT,
    PHANTOM_CAPITAL_INR,
    DHAN_NOTIONAL_WARNING_INR,
)
from domain.constants.market import (
    DEFAULT_TICK_SIZE,
    DEFAULT_EXCHANGE_SEGMENT_FALLBACK,
    DEFAULT_EXCHANGE,
    DEFAULT_DERIVATIVES_EXCHANGE,
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
from domain.constants.observability import (
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

from domain.constants.exchanges import (  # noqa: F401
    BCD,
    BFO,
    BSE,
    CDS,
    IDX,
    MCX,
    NFO,
    NSE,
    SHORT_TO_SEGMENT,
    WIRE_BSE_CURRENCY,
    WIRE_BSE_EQ,
    WIRE_BSE_FNO,
    WIRE_IDX,
    WIRE_MCX_COMM,
    WIRE_NSE_CURRENCY,
    WIRE_NSE_EQ,
    WIRE_NSE_FNO,
)

__all__ = [
    # exchanges
    "NSE",
    "BSE",
    "NFO",
    "BFO",
    "MCX",
    "CDS",
    "BCD",
    "IDX",
    "WIRE_NSE_EQ",
    "WIRE_BSE_EQ",
    "WIRE_NSE_FNO",
    "WIRE_BSE_FNO",
    "WIRE_MCX_COMM",
    "WIRE_NSE_CURRENCY",
    "WIRE_BSE_CURRENCY",
    "WIRE_IDX",
    "SHORT_TO_SEGMENT",
    # timeouts
    "DEFAULT_STOP_TIMEOUT_SECONDS",
    "DEFAULT_HTTP_TIMEOUT_SECONDS",
    "MIN_SLEEP_SECONDS",
    "QUOTE_CACHE_TTL_SECONDS",
    "HISTORY_CACHE_TTL_SECONDS",
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
    "DEFAULT_DERIVATIVES_EXCHANGE",
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
]
