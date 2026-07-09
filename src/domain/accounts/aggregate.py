"""Account Aggregate Root.

Thin, thread-safe wrapper around the canonical
:class:`~domain.entities.account.Balance` value object. The aggregate owns the
account identity and balance state; positions and holdings are referenced by
instrument identity (composition via :class:`~domain.aggregates.position.PositionAggregate`),
not duplicated here.
"""

from __future__ import annotations

import threading
from decimal import Decimal

from domain.entities.account import Balance


class AccountAggregate:
    """Account Aggregate Root — owns account identity and balance state."""

    def __init__(self, account_id: str, *, balance: Balance | None = None) -> None:
        self._account_id = account_id
        self._balance = balance or Balance()
        self._lock = threading.RLock()

    # ── Identity (read-only, lock-free) ────────────────────────────

    @property
    def account_id(self) -> str:
        return self._account_id

    # ── State (thread-safe read) ───────────────────────────────────

    @property
    def balance(self) -> Balance:
        """Current account balance snapshot (immutable)."""
        return self._balance

    @property
    def available_balance(self) -> Decimal:
        return self._balance.available_balance

    @property
    def used_margin(self) -> Decimal:
        return self._balance.used_margin

    # ── Lifecycle transitions ──────────────────────────────────────

    def update_balance(self, balance: Balance) -> None:
        """Replace the balance snapshot atomically."""
        with self._lock:
            self._balance = balance

    def has_sufficient(self, required: Decimal) -> bool:
        """Return True if available balance covers the required amount."""
        return self._balance.has_sufficient(required)

    # ── Equality (by identity) ─────────────────────────────────────

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, AccountAggregate):
            return NotImplemented
        return self._account_id == other._account_id

    def __hash__(self) -> int:
        return hash(self._account_id)

    def __repr__(self) -> str:
        return f"AccountAggregate({self._account_id})"
