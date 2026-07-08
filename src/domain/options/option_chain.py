"""OptionChain — first-class aggregate, composed of Option instruments.

    chain = nifty.option_chain()
    chain.atm              # Option (call at the ATM strike)
    chain.calls            # list[Option]
    chain.puts             # list[Option]
    chain.pcr()            # put/call open-interest ratio
    chain.max_pain()       # max-pain strike

Every option remains a full Instrument (it carries quote/greeks/state). The
underlying broker data is already normalized into the wrapped value object;
this class adds behavioral queries without becoming a God object.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING, Any

from domain.entities.options import OptionChain as OptionChainVO

if TYPE_CHECKING:
    from datetime import date

    from domain.ports.protocols import DataProvider


class OptionChain:
    """Rich query surface over a normalized option-chain snapshot."""

    def __init__(self, chain: OptionChainVO, *, provider: "DataProvider | None" = None) -> None:
        self._chain = chain
        self._provider = provider

    # ── Identity / state (read-through) ─────────────────────────────

    @property
    def underlying(self) -> str:
        return self._chain.underlying

    @property
    def exchange(self) -> str:
        return self._chain.exchange

    @property
    def expiry(self) -> str:
        return self._chain.expiry

    @property
    def expiries(self) -> tuple[str, ...]:
        return (self._chain.expiry,) if self._chain.expiry else ()

    @property
    def spot(self) -> Decimal | None:
        return self._chain.spot

    @property
    def strikes(self):
        return self._chain.strikes

    # ── Queries ─────────────────────────────────────────────────────

    def _atm_strike(self) -> Decimal | None:
        spot = self._chain.spot
        if spot is None or not self._chain.strikes:
            return None
        return min(
            (s.strike for s in self._chain.strikes),
            key=lambda k: abs(k - spot),
        )

    @property
    def atm(self):
        """The ATM call as a full Option instrument (``chain.atm.greeks.delta``)."""
        from domain.instruments.instrument import Option

        strike = self._atm_strike()
        if strike is None:
            return None
        row = next((s for s in self._chain.strikes if s.strike == strike), None)
        if row is None:
            return None
        return Option.from_leg(
            self._chain.underlying,
            self._chain.exchange,
            self._chain.expiry,
            strike,
            "CE",
            row.call,
            provider=self._provider,
        )

    @property
    def calls(self):
        from domain.instruments.instrument import Option

        return [
            Option.from_leg(
                self._chain.underlying,
                self._chain.exchange,
                self._chain.expiry,
                s.strike,
                "CE",
                s.call,
                provider=self._provider,
            )
            for s in self._chain.strikes
        ]

    @property
    def puts(self):
        from domain.instruments.instrument import Option

        return [
            Option.from_leg(
                self._chain.underlying,
                self._chain.exchange,
                self._chain.expiry,
                s.strike,
                "PE",
                s.put,
                provider=self._provider,
            )
            for s in self._chain.strikes
        ]

    def pcr(self) -> Decimal | None:
        """Put/Call ratio from open interest across the chain."""
        call_oi = sum((s.call.oi or 0) for s in self._chain.strikes)
        put_oi = sum((s.put.oi or 0) for s in self._chain.strikes)
        if call_oi == 0:
            return None
        return Decimal(put_oi) / Decimal(call_oi)

    def max_pain(self) -> Decimal | None:
        """Strike at which total option-writer payout is minimized."""
        strikes = [s.strike for s in self._chain.strikes]
        if not strikes:
            return None
        pain: dict[Decimal, int] = {}
        for k in strikes:
            total = 0
            for s in self._chain.strikes:
                coi = s.call.oi or 0
                poi = s.put.oi or 0
                total += coi * max(0, int(s.strike - k)) + poi * max(0, int(k - s.strike))
            pain[k] = total
        return min(pain, key=pain.get)

    def subscribe(self, callback=None, *, depth: bool = False):
        """Subscribe the underlying instrument (live data lives on the parent)."""
        if self._provider is None:
            return None
        from domain.instruments.instrument import Instrument
        from domain.instruments.instrument_id import InstrumentId

        underlying = Instrument(
            InstrumentId.index(self._chain.exchange, self._chain.underlying),
            data_provider=self._provider,
        )
        return underlying.subscribe(callback or (lambda *a, **k: None), depth=depth)

    def __repr__(self) -> str:
        return (
            f"OptionChain(underlying={self._chain.underlying}, "
            f"expiry={self._chain.expiry}, strikes={len(self._chain.strikes)})"
        )
