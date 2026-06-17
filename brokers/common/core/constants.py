"""Canonical constants for the broker-agnostic core.

This module is the single source of truth for numeric and string defaults
that were previously scattered across 25+ files (see the SHOTGUN-SURGERY
audit, SMELL-1 through SMELL-14). Every other module MUST import from here
instead of inlining the literal.

Rules of use
------------
* Broker-specific segments live in the broker's own ``segments.py`` or
  ``segment_mapper.py`` (e.g. ``brokers/dhan/segments.py``,
  ``brokers/upstox/instruments/segment_mapper.py``).
* Wire-format exchange codes (the values brokers send on the wire) are
  re-exported from :mod:`brokers.common.core.exchange_segments` once that
  module is introduced. Until then, the *defaults* — the segments the
  system falls back to when an exchange identifier is missing or
  unknown — are centralised here.
* Time-based constants are in seconds (with ``_MS`` / ``_MIN`` suffix
  where the unit is non-obvious).
* Money-related constants are :class:`decimal.Decimal`, never ``float``.

Anything added to this file MUST also be added to the
``test_constants_uniqueness`` AST test so future drift is caught at PR
time.
"""
from __future__ import annotations

from datetime import timedelta, timezone
from decimal import Decimal

# ── Timeouts (seconds) ─────────────────────────────────────────────────────

#: Default ``stop(timeout_seconds=...)`` for any ManagedService.
#: Used by LifecycleManager.drain, HttpObservabilityServer, Dhan depth feeds,
#: and the Dhan connection's ``close()`` call. Five seconds is the value
#: the certification report (M-7) verified empirically; do not change
#: without re-running the chaos tests in ``tests/chaos/``.
DEFAULT_STOP_TIMEOUT_SECONDS: float = 5.0

#: Default HTTP client timeout (Upstox http.py default is 15s).
DEFAULT_HTTP_TIMEOUT_SECONDS: float = 15.0

# ── Resilience timing ──────────────────────────────────────────────────────

#: Maximum delay between retry attempts (milliseconds). Must match
#: ``ExponentialBackoff._max_delay_ms`` and ``RetryConfig.max_retry_delay_ms``.
MAX_RETRY_DELAY_MS: int = 30_000

#: Base delay between retry attempts (milliseconds).
RETRY_BASE_DELAY_MS: int = 1_000

#: Maximum number of retry attempts.
MAX_RETRY_ATTEMPTS: int = 3

#: Default number of consecutive failures that opens the circuit breaker.
CIRCUIT_BREAKER_FAILURE_THRESHOLD: int = 5

#: Number of consecutive successes in HALF_OPEN that closes the breaker.
CIRCUIT_BREAKER_SUCCESS_THRESHOLD: int = 3

#: How long the breaker stays OPEN before allowing a probe (milliseconds).
CIRCUIT_BREAKER_OPEN_DURATION_MS: int = 30_000

#: Multiplier between successive backoff delays.
BACKOFF_MULTIPLIER: float = 2.0

#: ±Jitter applied to backoff delays (0.0 = no jitter, 0.2 = ±20%).
BACKOFF_JITTER: float = 0.2

#: Minimum sleep chunk used by rate-limiter and reconciliation tick (seconds).
MIN_SLEEP_SECONDS: float = 0.001

# ── Auth / token lifecycle ─────────────────────────────────────────────────

#: Recommended buffer before a token is "about to expire" (seconds).
#: ``TokenState.refresh_recommended`` and ``AuthManager.ensure_valid``
#: both default to this.
TOKEN_REFRESH_RECOMMENDED_BUFFER_SECONDS: float = 300.0

#: Actual buffer used by the Dhan ``TokenRefreshScheduler`` (seconds).
#: Larger than the common default because Dhan access tokens have a
#: 24h lifetime and we want to refresh well before the next market open.
#: **REQUIRES DOMAIN VERIFICATION** — must match Dhan token-policy docs.
DHAN_TOKEN_REFRESH_BUFFER_SECONDS: float = 600.0

#: Dhan token-scheduler poll interval (seconds).
DHAN_TOKEN_SCHEDULER_INTERVAL_SECONDS: int = 20 * 60  # 1_200

#: Dhan access-token lifetime (seconds).
DHAN_TOKEN_LIFETIME_SECONDS: int = 24 * 60 * 60  # 86_400

#: Seconds a successful refresh must hold before another refresh is allowed.
#: Prevents token-storm on flaky networks. Used by Dhan http_client.
DHAN_REFRESH_COOLDOWN_SECONDS: int = 60

#: Clock-skew tolerance for token expiry (seconds).
TOKEN_CLOCK_SKEW_SECONDS: float = 30.0

# ── Risk / capital ─────────────────────────────────────────────────────────

#: Daily-loss cap (percent) — RiskManager default.
RISK_DAILY_LOSS_PERCENT: float = 5.0

#: Per-position exposure cap (percent) — RiskManager default.
RISK_POSITION_PERCENT: float = 20.0

#: Gross exposure cap (percent of capital) — RiskManager default.
RISK_GROSS_PERCENT: float = 100.0

#: Phantom capital (INR) used when ``capital_fn`` is not configured. This
#: MUST be replaced with a real capital source before live trading; the
#: production-readiness check (REF-17) fails closed if the operator
#: leaves ``RISK_FAIL_OPEN=1`` set.
PHANTOM_CAPITAL_INR: Decimal = Decimal("1_000_000")

#: High-notional INR threshold above which Dhan order placement logs
#: a warning. Dhan's "kill switch" advisory is on a similar value but
#: is governed by the broker, not by us.
DHAN_NOTIONAL_WARNING_INR: Decimal = Decimal("50_000")

# ── OMS / reconciliation cadence ──────────────────────────────────────────

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

# ── Market data defaults ───────────────────────────────────────────────────

#: Default tick size for FNO contracts (INR). **REQUIRES DOMAIN
#: VERIFICATION** — NSE FNO tick size can change. Both
#: ``core.Instrument.tick_size`` and ``services.CanonicalInstrument.tick_size``
#: should reference this.
DEFAULT_TICK_SIZE: Decimal = Decimal("0.05")

#: Default exchange segment for fall-through when EXCHANGE_TO_SEGMENT misses.
#: Broker-specific — the canonical canonical "NSE_EQ" wire code is owned by
#: each broker's segments module. This constant is the placeholder string
#: used in the few places that need a literal and cannot import the broker
#: module.
DEFAULT_EXCHANGE_SEGMENT_FALLBACK: str = "NSE_EQ"

#: Default exchange identifier (no wire suffix) used in helpers that do not
#: know the broker. Same caveat as above.
DEFAULT_EXCHANGE: str = "NSE"

# ── Market hours (NSE equity) ──────────────────────────────────────────────

#: NSE equity market open hour (24h IST).
NSE_OPEN_HOUR_IST: int = 9

#: NSE equity market open minute.
NSE_OPEN_MINUTE_IST: int = 15

#: NSE equity market close hour.
NSE_CLOSE_HOUR_IST: int = 15

#: NSE equity market close minute.
NSE_CLOSE_MINUTE_IST: int = 30

#: MCX commodity market open hour (24h IST).
MCX_OPEN_HOUR_IST: int = 9

#: MCX commodity market open minute.
MCX_OPEN_MINUTE_IST: int = 0

#: MCX commodity market close hour.
MCX_CLOSE_HOUR_IST: int = 23

#: MCX commodity market close minute.
MCX_CLOSE_MINUTE_IST: int = 30

# ── Timezone (IST = UTC+5:30, no DST) ─────────────────────────────────────

#: Fixed IST offset. Use this instead of ``timezone(timedelta(hours=5,
#: minutes=30))`` scattered across files. ``ZoneInfo("Asia/Kolkata")`` is
#: the preferred public alternative and is used in some modules; both
#: represent the same offset.
IST_OFFSET = timezone(timedelta(hours=5, minutes=30))

# ── Observability / HTTP server ────────────────────────────────────────────

#: Default bind address for HttpObservabilityServer.
OBSERVABILITY_DEFAULT_HOST: str = "127.0.0.1"

#: Default bind port for HttpObservabilityServer.
OBSERVABILITY_DEFAULT_PORT: int = 8765

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

# ── Upstox-specific (centred here for consistency, but owned by the
#    broker; the broker's segment_mapper.py is the canonical source) ───────

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

# ── Re-exports for convenience ────────────────────────────────────────────

__all__ = [
    "BACKOFF_JITTER",
    "BACKOFF_MULTIPLIER",
    "BATCH_MAX_WORKERS",
    "CIRCUIT_BREAKER_FAILURE_THRESHOLD",
    "CIRCUIT_BREAKER_OPEN_DURATION_MS",
    "CIRCUIT_BREAKER_SUCCESS_THRESHOLD",
    "DAILY_PNL_POLL_INTERVAL_SECONDS",
    "DAILY_PNL_ROLLOVER_HOUR_IST",
    "DEFAULT_EXCHANGE",
    "DEFAULT_EXCHANGE_SEGMENT_FALLBACK",
    "DEFAULT_HISTORY_PAGE_DAYS",
    "DEFAULT_HTTP_TIMEOUT_SECONDS",
    "DEFAULT_LOG_LEVEL",
    "DEFAULT_MAX_DAILY_DAYS",
    "DEFAULT_MAX_INTRADAY_DAYS",
    "DEFAULT_STOP_TIMEOUT_SECONDS",
    "DEFAULT_TICK_SIZE",
    "DEAD_LETTER_QUEUE_MAX_SIZE",
    "DHAN_DEPTH_20_MAX_INSTRUMENTS",
    "DHAN_DEPTH_200_MAX_INSTRUMENTS",
    "DHAN_IDEMPOTENCY_MAX_SIZE",
    "DHAN_IDEMPOTENCY_TTL_SECONDS",
    "DHAN_NOTIONAL_WARNING_INR",
    "DHAN_REFRESH_COOLDOWN_SECONDS",
    "DHAN_TOKEN_LIFETIME_SECONDS",
    "DHAN_TOKEN_REFRESH_BUFFER_SECONDS",
    "DHAN_TOKEN_SCHEDULER_INTERVAL_SECONDS",
    "IST_OFFSET",
    "MAX_RETRY_ATTEMPTS",
    "MAX_RETRY_DELAY_MS",
    "MCX_CLOSE_HOUR_IST",
    "MCX_CLOSE_MINUTE_IST",
    "MCX_OPEN_HOUR_IST",
    "MCX_OPEN_MINUTE_IST",
    "MIN_SLEEP_SECONDS",
    "NSE_CLOSE_HOUR_IST",
    "NSE_CLOSE_MINUTE_IST",
    "NSE_OPEN_HOUR_IST",
    "NSE_OPEN_MINUTE_IST",
    "OBSERVABILITY_DEFAULT_HOST",
    "OBSERVABILITY_DEFAULT_PORT",
    "PHANTOM_CAPITAL_INR",
    "PROCESSED_TRADE_CLEANUP_INTERVAL_SECONDS",
    "PROCESSED_TRADE_RETENTION_SECONDS",
    "RECONCILIATION_INTERVAL_SECONDS",
    "RETRY_BASE_DELAY_MS",
    "RISK_DAILY_LOSS_PERCENT",
    "RISK_GROSS_PERCENT",
    "RISK_POSITION_PERCENT",
    "THIRD_PARTY_LOG_LEVEL",
    "TOKEN_CLOCK_SKEW_SECONDS",
    "TOKEN_REFRESH_RECOMMENDED_BUFFER_SECONDS",
    "UPSTOX_DEFAULT_RATE_PER_SECOND",
    "UPSTOX_INSTRUMENT_CACHE_HOURS",
    "UPSTOX_WS_PING_INTERVAL_SECONDS",
    "UPSTOX_WS_PING_TIMEOUT_SECONDS",
]
