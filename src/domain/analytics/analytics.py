"""Analytics Aggregate Root — owns computed trading analytics.

Thread-safe wrapper that stores derived metrics (PnL, Sharpe, etc.)
as immutable snapshots, replacing state atomically under a lock.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class AnalyticsSnapshot:
    """Immutable snapshot of computed analytics."""

    total_pnl: Decimal = Decimal("0")
    realized_pnl: Decimal = Decimal("0")
    unrealized_pnl: Decimal = Decimal("0")
    win_rate: float = 0.0
    sharpe_ratio: float = 0.0
    max_drawdown: Decimal = Decimal("0")
    trade_count: int = 0


class AnalyticsAggregate:
    """Thread-safe analytics aggregate that owns computed metrics."""

    def __init__(self, account_id: str) -> None:
        self._account_id = account_id
        self._snapshot = AnalyticsSnapshot()
        self._lock = threading.RLock()

    @property
    def account_id(self) -> str:
        return self._account_id

    @property
    def snapshot(self) -> AnalyticsSnapshot:
        return self._snapshot

    def update(self, snapshot: AnalyticsSnapshot) -> None:
        with self._lock:
            self._snapshot = snapshot

    def record_trade(self, pnl: Decimal) -> None:
        with self._lock:
            old = self._snapshot
            new_total = old.total_pnl + pnl
            new_realized = old.realized_pnl + pnl
            new_count = old.trade_count + 1
            self._snapshot = AnalyticsSnapshot(
                total_pnl=new_total,
                realized_pnl=new_realized,
                unrealized_pnl=old.unrealized_pnl,
                win_rate=old.win_rate,
                sharpe_ratio=old.sharpe_ratio,
                max_drawdown=old.max_drawdown,
                trade_count=new_count,
            )

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, AnalyticsAggregate):
            return NotImplemented
        return self._account_id == other._account_id

    def __hash__(self) -> int:
        return hash(self._account_id)

    def __repr__(self) -> str:
        return f"AnalyticsAggregate({self._account_id}, trades={self._snapshot.trade_count})"
