"""Pre-trade risk management.

Risk checks run inside the OMS lock before an order is submitted. All checks
are deterministic and read-only on the provided state.

Concurrency contract (Phase A / A2 + A3)
-----------------------------------------
Every mutator on :class:`RiskManager` is protected by an internal
``threading.RLock``. The previous implementation had no lock, which meant
``set_kill_switch`` and ``update_daily_pnl`` could be observed mid-update
by a concurrent ``check_order`` call. This was acceptable only because the
OMS held an outer lock for the place_order path; anything outside the OMS
(operator CLI, kill-switch webhook, dashboard query) raced.

The fix is internal to :class:`RiskManager` so the contract holds for any
caller, OMS or not.

Daily PnL rollover (Phase A / A2)
---------------------------------
``_daily_pnl`` is now reset by :meth:`reset_daily_pnl`, which must be
called by an external scheduler at the configured rollover hour (default
00:00 IST). :class:`brokers.common.oms.daily_pnl_reset_scheduler.DailyPnlResetScheduler`
is the canonical implementation. Without that scheduler, the running
total will accumulate across the IST 00:00 boundary and the daily-loss
check will block orders the next morning.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal

from brokers.common.core.domain import Order
from brokers.common.oms.position_manager import PositionManager

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RiskConfig:
    max_daily_loss_pct: Decimal = Decimal("5")  # of capital
    max_position_pct: Decimal = Decimal("20")   # of capital per symbol
    max_gross_exposure_pct: Decimal = Decimal("100")  # of capital
    kill_switch: bool = False


@dataclass(frozen=True)
class RiskResult:
    allowed: bool
    reason: str | None = None


class RiskManager:
    """Deterministic, stateless risk checks.

    State held:

    * ``_config`` — frozen :class:`RiskConfig`; replaced atomically on
      :meth:`set_kill_switch`.
    * ``_daily_pnl`` — running total of realised + unrealised PnL for
      the current day. Reset to 0 by :meth:`reset_daily_pnl`.

    All state mutations are guarded by ``_lock``. ``check_order`` takes
    the lock for the duration of the read so an interleaved
    ``set_kill_switch`` or ``update_daily_pnl`` cannot produce a
    half-observed state.
    """

    def __init__(
        self,
        position_manager: PositionManager,
        config: RiskConfig,
        capital_fn: Callable[[], Decimal] | None = None,
    ) -> None:
        self._position_manager = position_manager
        self._config = config
        self._capital_fn = capital_fn or (lambda: Decimal("0"))
        self._daily_pnl: Decimal = Decimal("0")
        # A2: lock that protects _config, _daily_pnl, and the derived
        # reads in check_order. RLock (not Lock) so the OMS may
        # legitimately call check_order from inside its own critical
        # section without deadlocking.
        self._lock = threading.RLock()
        # Observability: monotonic counters for reset / kill-switch
        # events. Useful for alerting ("daily PnL reset fired today").
        self._reset_count: int = 0
        self._kill_switch_toggles: int = 0
        self._last_reset_at: float = 0.0  # time.time() at last reset

    # ── Public API ─────────────────────────────────────────────────────────

    def check_order(self, order: Order) -> RiskResult:
        """Check whether ``order`` passes all configured risk limits.

        Thread-safe. Holds ``_lock`` for the duration of the read so a
        concurrent ``set_kill_switch`` cannot produce a half-observed
        config.
        """
        with self._lock:
            if self._config.kill_switch:
                return RiskResult(False, "Kill switch is active")

            capital = self._capital_fn()
            if capital <= 0:
                return RiskResult(False, "Insufficient capital")

            notional = Decimal(order.quantity) * order.price if order.price > 0 else Decimal(order.quantity)

            # Per-symbol concentration
            current = self._position_manager.get_position(order.symbol, order.exchange)
            current_notional = Decimal(abs(current.quantity)) * current.avg_price if current else Decimal("0")
            if (current_notional + notional) / capital * 100 > self._config.max_position_pct:
                return RiskResult(False, f"Exceeds max position pct for {order.symbol}")

            # Gross exposure
            positions = self._position_manager.get_positions()
            gross = sum(Decimal(abs(p.quantity)) * p.avg_price for p in positions)
            if (gross + notional) / capital * 100 > self._config.max_gross_exposure_pct:
                return RiskResult(False, "Exceeds max gross exposure pct")

            # Daily loss
            if self._daily_pnl < 0 and abs(self._daily_pnl) / capital * 100 >= self._config.max_daily_loss_pct:
                return RiskResult(False, "Daily loss limit reached")

            return RiskResult(True)

    def update_daily_pnl(self, pnl: Decimal) -> None:
        """Update running daily PnL (called by portfolio manager).

        Thread-safe. Replaces the running total atomically; readers
        under ``_lock`` will see either the old or the new value, not a
        partially-written one.
        """
        with self._lock:
            self._daily_pnl = pnl

    def set_kill_switch(self, active: bool) -> None:
        """Enable or disable the kill switch by replacing the frozen config.

        Thread-safe. A concurrent ``check_order`` will see either the
        old config (kill switch as it was) or the new one (kill switch
        flipped), but never a torn read of the dataclass.
        """
        with self._lock:
            previous = self._config.kill_switch
            self._config = RiskConfig(
                max_daily_loss_pct=self._config.max_daily_loss_pct,
                max_position_pct=self._config.max_position_pct,
                max_gross_exposure_pct=self._config.max_gross_exposure_pct,
                kill_switch=active,
            )
            if previous != active:
                self._kill_switch_toggles += 1
                logger.warning(
                    "kill_switch_toggled",
                    extra={"new_state": active, "previous": previous},
                )

    def reset_daily_pnl(self) -> None:
        """Reset the daily PnL to zero.

        Called by :class:`DailyPnlResetScheduler` at the configured
        rollover hour (default 00:00 IST). Safe to call manually from
        tests or operator scripts.

        Thread-safe. Increments ``_reset_count`` and records
        ``_last_reset_at`` so an SRE can confirm the rollover fired.
        """
        import time as _time
        with self._lock:
            self._daily_pnl = Decimal("0")
            self._reset_count += 1
            self._last_reset_at = _time.time()
        logger.info("daily_pnl_reset", extra={"reset_count": self._reset_count})

    # ── Observability (read-only) ────────────────────────────────────────

    @property
    def daily_pnl(self) -> Decimal:
        """Current daily PnL snapshot. Thread-safe."""
        with self._lock:
            return self._daily_pnl

    @property
    def kill_switch(self) -> bool:
        """Current kill-switch state. Thread-safe."""
        with self._lock:
            return self._config.kill_switch

    def snapshot(self) -> dict:
        """Return a JSON-serializable view of risk-manager state.

        Useful for ``/healthz`` and SRE dashboards. Locks are taken
        only briefly to read the scalar fields.
        """
        import time as _time
        with self._lock:
            return {
                "kill_switch": self._config.kill_switch,
                "daily_pnl": str(self._daily_pnl),
                "max_daily_loss_pct": str(self._config.max_daily_loss_pct),
                "max_position_pct": str(self._config.max_position_pct),
                "max_gross_exposure_pct": str(self._config.max_gross_exposure_pct),
                "reset_count": self._reset_count,
                "kill_switch_toggles": self._kill_switch_toggles,
                "last_reset_at": self._last_reset_at,
                "seconds_since_last_reset": (
                    _time.time() - self._last_reset_at if self._last_reset_at > 0 else None
                ),
            }
