"""OptionChain Aggregate Root.

Thin, thread-safe wrapper around the canonical
:class:`~domain.entities.options.OptionChain` value object. Identity is the
``(underlying, expiry)`` pair. Provides rich query operations (ATM/ITM/OTM)
without turning the entity into a God object — the chain data stays immutable
and queries are pure functions over the enclosed snapshot.
"""

from __future__ import annotations

import threading
from decimal import Decimal

from domain.entities.options import OptionChain, OptionStrike


class OptionChainAggregate:
    """OptionChain Aggregate Root — owns chain identity, data, and queries."""

    def __init__(self, chain: OptionChain) -> None:
        self._chain = chain
        self._lock = threading.RLock()

    # ── Identity (read-only, lock-free) ────────────────────────────

    @property
    def underlying(self) -> str:
        return self._chain.underlying

    @property
    def expiry(self) -> str:
        return self._chain.expiry

    # ── State (thread-safe read) ───────────────────────────────────

    @property
    def chain(self) -> OptionChain:
        """Current option chain snapshot (immutable)."""
        return self._chain

    @property
    def strikes(self) -> tuple[OptionStrike, ...]:
        with self._lock:
            return tuple(self._chain.strikes)

    @property
    def spot(self) -> Decimal | None:
        return self._chain.spot

    # ── Queries (pure, read-only) ──────────────────────────────────

    def atm_strike(self) -> Decimal | None:
        """Return the strike closest to spot, or None if no spot/strikes."""
        spot = self._chain.spot
        if spot is None or not self._chain.strikes:
            return None
        return min(
            (s.strike for s in self._chain.strikes),
            key=lambda k: abs(k - spot),
        )

    def itm_calls(self) -> tuple[OptionStrike, ...]:
        """Call strikes in-the-money relative to spot (strike < spot)."""
        spot = self._chain.spot
        if spot is None:
            return ()
        return tuple(s for s in self._chain.strikes if s.strike < spot)

    def otm_calls(self) -> tuple[OptionStrike, ...]:
        """Call strikes out-of-the-money relative to spot (strike > spot)."""
        spot = self._chain.spot
        if spot is None:
            return ()
        return tuple(s for s in self._chain.strikes if s.strike > spot)

    # ── Equality (by identity) ─────────────────────────────────────

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, OptionChainAggregate):
            return NotImplemented
        return (
            self._chain.underlying == other._chain.underlying
            and self._chain.expiry == other._chain.expiry
        )

    def __hash__(self) -> int:
        return hash((self._chain.underlying, self._chain.expiry))

    def __repr__(self) -> str:
        return (
            f"OptionChainAggregate(underlying={self._chain.underlying}, "
            f"expiry={self._chain.expiry}, strikes={len(self._chain.strikes)})"
        )
