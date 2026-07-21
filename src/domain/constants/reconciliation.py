"""Reconciliation and OMS cadence constants (REF-13)."""

from __future__ import annotations

# ── OMS / reconciliation ─────────────────────────────────────────────────────

#: SQLite ``busy_timeout`` (milliseconds) applied to order/execution stores.
SQLITE_BUSY_TIMEOUT_MS: int = 5_000

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
PROCESSED_TRADE_RETENTION_SECONDS: int = 0  # 0 = no in-memory eviction (durable dedup)

#: Periodic cleanup interval for ProcessedTradeRepository.
PROCESSED_TRADE_CLEANUP_INTERVAL_SECONDS: int = 60 * 60  # 1h

# ── Batching / threading ─────────────────────────────────────────────────────

#: Number of worker threads used by BatchFetchMixin.
BATCH_MAX_WORKERS: int = 5

# ── Dead-letter queue ────────────────────────────────────────────────────────

#: Maximum events the DeadLetterQueue will buffer before dropping the
#: oldest. Larger values consume more memory.
DEAD_LETTER_QUEUE_MAX_SIZE: int = 10_000

__all__ = [
    "BATCH_MAX_WORKERS",
    "DAILY_PNL_POLL_INTERVAL_SECONDS",
    "DAILY_PNL_ROLLOVER_HOUR_IST",
    "DEAD_LETTER_QUEUE_MAX_SIZE",
    "PROCESSED_TRADE_CLEANUP_INTERVAL_SECONDS",
    "PROCESSED_TRADE_RETENTION_SECONDS",
    "RECONCILIATION_INTERVAL_SECONDS",
    "SQLITE_BUSY_TIMEOUT_MS",
]
