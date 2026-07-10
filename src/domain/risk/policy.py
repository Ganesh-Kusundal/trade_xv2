"""Pure risk policy objects — composable, testable domain rules.

Each policy is a frozen (or lightly stateful) value object with a single
``check(...)`` method that returns a :class:`RiskResult`. Policies are
composable: a ``RiskGate`` chains multiple policies and short-circuits on the
first rejection.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from domain.constants.risk import DEFAULT_DAILY_LOSS_LIMIT_INR


@dataclass(frozen=True, slots=True)
class RiskResult:
    """Outcome of a risk check — approved or rejected with a reason."""

    approved: bool
    reason: str = ""


@dataclass(frozen=True, slots=True)
class OrderNotionalLimit:
    """Rejects orders whose notional exceeds a fixed cap."""

    max_notional: Decimal = Decimal("1000000")

    def check(self, order_notional: Decimal) -> RiskResult:
        if order_notional > self.max_notional:
            return RiskResult(False, f"notional {order_notional} exceeds limit {self.max_notional}")
        return RiskResult(True)


@dataclass(frozen=True, slots=True)
class ConcentrationLimit:
    """Rejects orders that would make one symbol too large a share of portfolio notional."""

    max_pct: Decimal = Decimal("0.20")

    def check(self, order_notional: Decimal, portfolio_notional: Decimal) -> RiskResult:
        if portfolio_notional <= 0:
            return RiskResult(True)
        ratio = order_notional / portfolio_notional
        if ratio > self.max_pct:
            return RiskResult(False, f"concentration {ratio:.2%} exceeds limit {self.max_pct:.2%}")
        return RiskResult(True)


@dataclass(frozen=True, slots=True)
class GrossExposureLimit:
    """Rejects when total portfolio exposure exceeds a percentage of capital."""

    max_pct: Decimal = Decimal("1.0")

    def check(self, total_exposure: Decimal, capital: Decimal) -> RiskResult:
        if capital <= 0:
            return RiskResult(False, "capital must be positive")
        ratio = total_exposure / capital
        if ratio > self.max_pct:
            return RiskResult(False, f"gross exposure {ratio:.2%} exceeds limit {self.max_pct:.2%}")
        return RiskResult(True)


@dataclass
class DailyLossCircuitBreaker:
    """Stateful policy: trips when cumulative intraday PnL loss exceeds a threshold.

    ``record_pnl(pnl)`` is called as fills/price updates arrive.
    ``check()`` returns REJECTED once the breaker has tripped.
    """

    daily_loss_limit: Decimal = DEFAULT_DAILY_LOSS_LIMIT_INR
    cumulative_pnl: Decimal = field(default=Decimal("0"), init=False)
    is_tripped: bool = field(default=False, init=False)

    def record_pnl(self, pnl: Decimal) -> None:
        """Accumulate PnL; trip the breaker if the daily loss limit is breached."""
        self.cumulative_pnl += pnl
        if self.cumulative_pnl <= -self.daily_loss_limit:
            self.is_tripped = True

    def reset(self) -> None:
        """Reset at start of new trading day."""
        self.cumulative_pnl = Decimal("0")
        self.is_tripped = False

    def check(self) -> RiskResult:
        if self.is_tripped:
            return RiskResult(
                False,
                f"daily loss {self.cumulative_pnl} breached limit {self.daily_loss_limit}",
            )
        return RiskResult(True)


class KillSwitch:
    """Manually activated kill switch — rejects all orders when active."""

    def __init__(self) -> None:
        self._active = False

    def activate(self) -> None:
        self._active = True

    def deactivate(self) -> None:
        self._active = False

    @property
    def is_active(self) -> bool:
        return self._active

    def check(self) -> RiskResult:
        if self._active:
            return RiskResult(False, "kill switch active — all orders rejected")
        return RiskResult(True)


def check_daily_loss_pct(
    daily_pnl: Decimal,
    capital: Decimal,
    max_daily_loss_pct: Decimal,
) -> RiskResult:
    """Reject when cumulative daily loss reaches ``max_daily_loss_pct`` of capital.

    ``max_daily_loss_pct`` is a percentage (e.g. ``Decimal("2")`` = 2%).
    Zero or negative limit disables the check (always approved).
    """
    if max_daily_loss_pct <= 0 or capital <= 0:
        return RiskResult(True)
    if daily_pnl < 0 and abs(daily_pnl) / capital * 100 >= max_daily_loss_pct:
        return RiskResult(
            False,
            f"daily loss {daily_pnl} breached {max_daily_loss_pct}% of capital {capital}",
        )
    return RiskResult(True)


def check_paper_daily_loss(
    daily_pnl: float | Decimal,
    capital: float | Decimal,
    max_daily_loss_pct: float | Decimal,
) -> RiskResult:
    """Paper/float adapter for :func:`check_daily_loss_pct`.

    Converts paper-engine floats to :class:`Decimal` then delegates to the
    pure domain percentage check. Use when config has a non-zero
    ``max_daily_loss_pct``.
    """
    return check_daily_loss_pct(
        Decimal(str(daily_pnl)),
        Decimal(str(capital)),
        Decimal(str(max_daily_loss_pct)),
    )


@dataclass(frozen=True, slots=True)
class RiskGate:
    """Composes multiple policies and short-circuits on the first rejection.

    This is the single entry point application workflows call for pre-trade risk.
    """

    notional: OrderNotionalLimit = field(default_factory=OrderNotionalLimit)
    concentration: ConcentrationLimit = field(default_factory=ConcentrationLimit)
    gross_exposure: GrossExposureLimit = field(default_factory=GrossExposureLimit)

    def check_order(
        self,
        order_notional: Decimal,
        portfolio_notional: Decimal,
        total_exposure: Decimal,
        capital: Decimal,
    ) -> RiskResult:
        r = self.notional.check(order_notional)
        if not r.approved:
            return r
        r = self.concentration.check(order_notional, portfolio_notional)
        if not r.approved:
            return r
        r = self.gross_exposure.check(total_exposure, capital)
        if not r.approved:
            return r
        return RiskResult(True)
