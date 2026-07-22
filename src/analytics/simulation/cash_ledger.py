"""Shared cash ledger — canonical implementation.

Two distinct capital notions are kept separate:

* ``SimulatedCashLedger`` — single source of truth for *session cash* when
  OMS is wired. It declines as fills consume capital; it is used only for
  session sizing (``session.capital``), never for risk checks.
* ``FixedAccountCapitalProvider`` — duck-typed ``CapitalProvider`` that
  returns the *account-size* capital (``config.initial_capital``) and never
  declines. ``RiskManager`` binds to this so risk % (position / gross /
  daily-loss) measure against fixed equity, exactly like live FixedCapital.
"""

from __future__ import annotations

from decimal import Decimal


class SimulatedCashLedger:
    """Duck-typed portfolio_tracker: ``get_capital()`` + debit/credit."""

    __slots__ = ("_cash",)

    def __init__(self, initial: float) -> None:
        self._cash = float(initial)

    def get_capital(self) -> float:
        return self._cash

    def debit(self, amount: float) -> None:
        self._cash -= float(amount)

    def credit(self, amount: float) -> None:
        self._cash += float(amount)

    def apply_delta(self, delta: float) -> None:
        """Positive = credit (sell proceeds); negative = debit (buy cost)."""
        self._cash += float(delta)


class FixedAccountCapitalProvider:
    """Fixed account-size capital for RiskManager risk checks (PARITY).

    Returns ``config.initial_capital`` and never declines with fills, so a
    fully-invested book does not starve the loss / position / gross daily-loss
    checks of capital. Duck-typed to avoid an analytics -> application import.
    """

    __slots__ = ("_amount",)

    def __init__(self, amount: float) -> None:
        self._amount = Decimal(str(amount))

    def get_available_balance(self) -> Decimal:
        return self._amount
