"""Daily PnL tracking with edge-triggered risk-limit breach events.

Extracted from :class:`~application.oms._internal.risk_manager.RiskManager`.
Owns the running **session equity delta** (current equity − session-open
equity), the rolling-window loss-circuit-breaker delta recording, and the
``RISK_LIMIT_BREACHED`` publish logic.

Callers must pass session equity delta — not absolute book MTM (F5).

This module must NOT import from ``risk_manager`` (no circular deps).
"""

from __future__ import annotations

import logging
import time
from decimal import Decimal
from typing import Callable

from domain.events.types import EventType

from application.oms._internal.loss_circuit_breaker import LossCircuitBreaker
from application.oms._internal.risk_types import RiskConfig

logger = logging.getLogger(__name__)

#: Fraction of the daily-loss budget consumed before RISK_LIMIT_BREACHED
#: fires. Deliberately below 1.0 so operators get a warning before the
#: hard daily-loss check in check_order starts rejecting orders outright.
RISK_LIMIT_BREACH_THRESHOLD = Decimal("0.8")


class DailyPnlTracker:
    """Thread-unsafe daily-PnL accumulator.

    The owning :class:`~application.oms._internal.risk_manager.RiskManager`
    serialises access under its lock; this class stores the scalar and the
    edge-triggered breach flag and performs the side effects.
    """

    def __init__(
        self,
        config: RiskConfig,
        capital_provider: Callable[[], Decimal],
        loss_cb: LossCircuitBreaker,
        on_risk_event: Callable[[str, dict], None] | None = None,
    ) -> None:
        self._config = config
        self._capital_provider = capital_provider
        self._loss_cb = loss_cb
        self._on_risk_event = on_risk_event
        self._daily_pnl: Decimal = Decimal("0")
        self._risk_limit_breach_notified = False
        self._reset_count: int = 0
        self._last_reset_at: float = 0.0

    # -- State --

    @property
    def value(self) -> Decimal:
        """Current daily PnL snapshot."""
        return self._daily_pnl

    @property
    def reset_count(self) -> int:
        return self._reset_count

    @property
    def last_reset_at(self) -> float:
        return self._last_reset_at

    # -- Mutators --

    def update(self, pnl: Decimal) -> None:
        """Update session equity delta (called by TradingContext feed).

        ``pnl`` is the session equity delta from session-open equity
        (``current_equity − session_open_equity``), not absolute MTM.

        Records the change since the last feed tick in the loss circuit
        breaker, then publishes RISK_LIMIT_BREACHED if the daily-loss
        budget is mostly consumed.
        """
        previous_pnl = self._daily_pnl
        self._daily_pnl = Decimal(str(getattr(pnl, "amount", pnl)))

        # Incremental move since last tick (for the rolling loss CB).
        delta = self._daily_pnl - previous_pnl
        capital_raw = self._capital_provider()
        capital = Decimal(str(getattr(capital_raw, "amount", capital_raw)))
        self._loss_cb.record_loss(delta, capital)

        self._maybe_publish_risk_limit_breach(self._daily_pnl, capital)

    def reset(self) -> None:
        """Reset the daily PnL to zero.

        Increments ``reset_count`` and records ``last_reset_at`` so an SRE
        can confirm the rollover fired.
        """
        self._daily_pnl = Decimal("0")
        self._reset_count += 1
        self._last_reset_at = time.time()
        logger.info("daily_pnl_reset", extra={"reset_count": self._reset_count})

    def is_stale(self) -> bool:
        """True if the last reset happened before today (IST)."""
        if self._last_reset_at == 0.0:
            return True
        from datetime import datetime, timezone
        from zoneinfo import ZoneInfo

        ist = ZoneInfo("Asia/Kolkata")
        reset_date = datetime.fromtimestamp(self._last_reset_at, tz=ist).date()
        today = datetime.now(ist).date()
        return reset_date < today

    def _maybe_publish_risk_limit_breach(self, pnl: Decimal, capital: Decimal) -> None:
        """Publish RISK_LIMIT_BREACHED once when the daily-loss budget is
        mostly consumed, and again only after recovering and re-breaching
        (edge-triggered, not level-triggered, so this doesn't spam the
        event bus on every single MTM update while still in breach).
        """
        if (
            self._on_risk_event is None
            or capital <= 0
            or self._config.max_daily_loss_pct <= 0
        ):
            return
        loss_budget = capital * (self._config.max_daily_loss_pct / Decimal("100"))
        if loss_budget <= 0:
            return
        consumed = (abs(pnl) / loss_budget) if pnl < 0 else Decimal("0")
        breached = consumed >= RISK_LIMIT_BREACH_THRESHOLD
        if breached and not self._risk_limit_breach_notified:
            self._risk_limit_breach_notified = True
            self._on_risk_event(
                EventType.RISK_LIMIT_BREACHED.value,
                {
                    "rule": "max_daily_loss_pct",
                    "value": str(pnl),
                    "limit": str(self._config.max_daily_loss_pct),
                },
            )
        elif not breached:
            self._risk_limit_breach_notified = False
