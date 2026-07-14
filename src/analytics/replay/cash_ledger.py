"""Simulated cash ledger for PARITY-mode replay.

Single source of truth for session cash when OMS is wired. Session capital
is synced from this ledger after each fill — RiskManager still uses the
TradingContext capital_fn / provider for sizing checks against account size.
"""

from __future__ import annotations


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
