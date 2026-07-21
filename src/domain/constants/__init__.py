"""Constants package — re-exports all constants for backward compatibility.

This package splits the monolithic constants.py into focused sub-modules:
- timeouts: Stop timeouts, HTTP timeouts, sleep intervals
- resilience: Retry, circuit breaker, backoff configuration
- auth: Token lifecycle and authentication constants
- risk: Risk thresholds, position limits, capital defaults
- market: Market hours, exchanges, tick sizes, timezone
- observability: HTTP server configuration
- oms: Time units, batching, dead-letter queue
- reconciliation: SQLite busy timeout, reconciliation intervals, PnL reset
- instrumentation: Logging levels
- history: Historical data defaults

All constants are re-exported here to maintain backward compatibility with
existing imports from ``domain.constants``.
"""

from __future__ import annotations

from domain.constants.auth import (
    DHAN_REFRESH_COOLDOWN_SECONDS,
    DHAN_TOKEN_LIFETIME_SECONDS,
    DHAN_TOKEN_REFRESH_BUFFER_SECONDS,
    DHAN_TOKEN_SCHEDULER_INTERVAL_SECONDS,
    TOKEN_CLOCK_SKEW_SECONDS,
    TOKEN_REFRESH_RECOMMENDED_BUFFER_SECONDS,
)
from domain.constants.defaults import DEFAULT_LOOKBACK_DAYS, DEFAULT_STORAGE_TIMEFRAME
from domain.constants.exchanges import (
    BCD,
    BFO,
    BSE,
    CDS,
    IDX,
    MCX,
    NFO,
    NSE,
    WIRE_BSE_CURRENCY,
    WIRE_BSE_EQ,
    WIRE_BSE_FNO,
    WIRE_IDX,
    WIRE_MCX_COMM,
    WIRE_NSE_CURRENCY,
    WIRE_NSE_EQ,
    WIRE_NSE_FNO,
)
from domain.constants.history import (
    DEFAULT_HISTORY_PAGE_DAYS,
    DEFAULT_MAX_DAILY_DAYS,
    DEFAULT_MAX_INTRADAY_DAYS,
)
from domain.constants.instrumentation import (
    DEFAULT_LOG_LEVEL,
    THIRD_PARTY_LOG_LEVEL,
)
from domain.constants.market import (
    ATR_PERIOD_DEFAULT,
    DEFAULT_DERIVATIVES_EXCHANGE,
    DEFAULT_EXCHANGE,
    DEFAULT_EXCHANGE_SEGMENT_FALLBACK,
    DEFAULT_TICK_SIZE,
    IST,
    IST_OFFSET,
    MCX_CLOSE_HOUR_IST,
    MCX_CLOSE_MINUTE_IST,
    MCX_OPEN_HOUR_IST,
    MCX_OPEN_MINUTE_IST,
    NSE_CLOSE_HOUR_IST,
    NSE_CLOSE_MINUTE_IST,
    NSE_OPEN_HOUR_IST,
    NSE_OPEN_MINUTE_IST,
    RSI_PERIOD_DEFAULT,
    SMA_WINDOW_DEFAULT,
)
from domain.constants.observability import (
    OBSERVABILITY_DEFAULT_HOST,
    OBSERVABILITY_DEFAULT_PORT,
)
from domain.constants.oms import (
    BATCH_MAX_WORKERS,
    DEAD_LETTER_QUEUE_MAX_SIZE,
    SECONDS_PER_DAY,
    SECONDS_PER_HOUR,
)
from domain.constants.reconciliation import (
    DAILY_PNL_POLL_INTERVAL_SECONDS,
    DAILY_PNL_ROLLOVER_HOUR_IST,
    PROCESSED_TRADE_CLEANUP_INTERVAL_SECONDS,
    PROCESSED_TRADE_RETENTION_SECONDS,
    RECONCILIATION_INTERVAL_SECONDS,
    SQLITE_BUSY_TIMEOUT_MS,
)
from domain.constants.resilience import (
    BACKOFF_JITTER,
    BACKOFF_MULTIPLIER,
    CIRCUIT_BREAKER_FAILURE_THRESHOLD,
    CIRCUIT_BREAKER_OPEN_DURATION_MS,
    CIRCUIT_BREAKER_SUCCESS_THRESHOLD,
    MAX_RETRY_ATTEMPTS,
    MAX_RETRY_DELAY_MS,
    RETRY_BASE_DELAY_MS,
)
from domain.constants.risk import (
    DHAN_NOTIONAL_WARNING_INR,
    PHANTOM_CAPITAL_INR,
    RISK_DAILY_LOSS_PERCENT,
    RISK_GROSS_PERCENT,
    RISK_LOSS_CB_COOLDOWN_SECONDS,
    RISK_LOSS_CB_WINDOW_SECONDS,
    RISK_LOSS_CIRCUIT_BREAKER_PERCENT,
    RISK_MARGIN_SAFETY_MULTIPLIER,
    RISK_POSITION_PERCENT,
)
from domain.constants.segments import (
    NSE_ELIGIBLE_SEGMENTS,
    is_nse_eligible,
    nse_eligible_segments,
)
from domain.constants.timeouts import (
    DEFAULT_HTTP_TIMEOUT_SECONDS,
    DEFAULT_STOP_TIMEOUT_SECONDS,
    HISTORY_CACHE_TTL_SECONDS,
    MIN_SLEEP_SECONDS,
    QUOTE_CACHE_TTL_SECONDS,
)

__all__ = [
    "ATR_PERIOD_DEFAULT",
    "BACKOFF_JITTER",
    "BACKOFF_MULTIPLIER",
    # batching
    "BATCH_MAX_WORKERS",
    "BCD",
    "BFO",
    "BSE",
    "CDS",
    "CIRCUIT_BREAKER_FAILURE_THRESHOLD",
    "CIRCUIT_BREAKER_OPEN_DURATION_MS",
    "CIRCUIT_BREAKER_SUCCESS_THRESHOLD",
    "DAILY_PNL_POLL_INTERVAL_SECONDS",
    "DAILY_PNL_ROLLOVER_HOUR_IST",
    # DLQ
    "DEAD_LETTER_QUEUE_MAX_SIZE",
    "DEFAULT_DERIVATIVES_EXCHANGE",
    "DEFAULT_EXCHANGE",
    "DEFAULT_EXCHANGE_SEGMENT_FALLBACK",
    # history
    "DEFAULT_HISTORY_PAGE_DAYS",
    "DEFAULT_HTTP_TIMEOUT_SECONDS",
    # logging
    "DEFAULT_LOG_LEVEL",
    "DEFAULT_LOOKBACK_DAYS",
    "DEFAULT_MAX_DAILY_DAYS",
    "DEFAULT_MAX_INTRADAY_DAYS",
    # timeouts
    "DEFAULT_STOP_TIMEOUT_SECONDS",
    "DEFAULT_STORAGE_TIMEFRAME",
    "DEFAULT_TICK_SIZE",
    "DHAN_NOTIONAL_WARNING_INR",
    "DHAN_REFRESH_COOLDOWN_SECONDS",
    "DHAN_TOKEN_LIFETIME_SECONDS",
    "DHAN_TOKEN_REFRESH_BUFFER_SECONDS",
    "DHAN_TOKEN_SCHEDULER_INTERVAL_SECONDS",
    "HISTORY_CACHE_TTL_SECONDS",
    "IDX",
    "IST",
    "IST_OFFSET",
    "MAX_RETRY_ATTEMPTS",
    # resilience
    "MAX_RETRY_DELAY_MS",
    "MCX",
    "MCX_CLOSE_HOUR_IST",
    "MCX_CLOSE_MINUTE_IST",
    "MCX_OPEN_HOUR_IST",
    "MCX_OPEN_MINUTE_IST",
    "MIN_SLEEP_SECONDS",
    "NFO",
    # exchanges
    "NSE",
    "NSE_CLOSE_HOUR_IST",
    "NSE_CLOSE_MINUTE_IST",
    "NSE_ELIGIBLE_SEGMENTS",
    "NSE_OPEN_HOUR_IST",
    "NSE_OPEN_MINUTE_IST",
    # observability
    "OBSERVABILITY_DEFAULT_HOST",
    "OBSERVABILITY_DEFAULT_PORT",
    "PHANTOM_CAPITAL_INR",
    "PROCESSED_TRADE_CLEANUP_INTERVAL_SECONDS",
    "PROCESSED_TRADE_RETENTION_SECONDS",
    "QUOTE_CACHE_TTL_SECONDS",
    # OMS
    "RECONCILIATION_INTERVAL_SECONDS",
    "RETRY_BASE_DELAY_MS",
    # risk
    "RISK_DAILY_LOSS_PERCENT",
    "RISK_GROSS_PERCENT",
    "RISK_LOSS_CB_COOLDOWN_SECONDS",
    "RISK_LOSS_CB_WINDOW_SECONDS",
    "RISK_LOSS_CIRCUIT_BREAKER_PERCENT",
    "RISK_MARGIN_SAFETY_MULTIPLIER",
    "RISK_POSITION_PERCENT",
    "RSI_PERIOD_DEFAULT",
    "SECONDS_PER_DAY",
    "SECONDS_PER_HOUR",
    "SMA_WINDOW_DEFAULT",
    "SQLITE_BUSY_TIMEOUT_MS",
    "THIRD_PARTY_LOG_LEVEL",
    "TOKEN_CLOCK_SKEW_SECONDS",
    # auth
    "TOKEN_REFRESH_RECOMMENDED_BUFFER_SECONDS",
    "WIRE_BSE_CURRENCY",
    "WIRE_BSE_EQ",
    "WIRE_BSE_FNO",
    "WIRE_IDX",
    "WIRE_MCX_COMM",
    "WIRE_NSE_CURRENCY",
    "WIRE_NSE_EQ",
    "WIRE_NSE_FNO",
    "is_nse_eligible",
    "nse_eligible_segments",
]
