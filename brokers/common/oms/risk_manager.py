"""Pre-trade risk management.

Risk checks run inside the OMS lock before an order is submitted. All checks
are deterministic and read-only on the provided state.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Callable

from brokers.common.core.domain import Order
from brokers.common.oms.position_manager import PositionManager


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
    """Deterministic, stateless risk checks."""

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

    # ── Public API ──────────────────────────────────────────────────────────

    def check_order(self, order: Order) -> RiskResult:
        """Check whether ``order`` passes all configured risk limits."""
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
        """Update running daily PnL (called by portfolio manager)."""
        self._daily_pnl = pnl

    def set_kill_switch(self, active: bool) -> None:
        """Enable or disable the kill switch by replacing the frozen config."""
        self._config = RiskConfig(
            max_daily_loss_pct=self._config.max_daily_loss_pct,
            max_position_pct=self._config.max_position_pct,
            max_gross_exposure_pct=self._config.max_gross_exposure_pct,
            kill_switch=active,
        )
