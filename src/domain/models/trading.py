"""Neutral trading DTOs for orchestrator boundary."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from domain.orders.intent import OrderIntent
    from domain.portfolio.account_view import AccountView
    from domain.portfolio.risk_profile import RiskProfile


@dataclass(frozen=True, slots=True)
class CandidateDTO:
    """Scanner output passed to execution layer."""

    symbol: str
    exchange: str
    score: Decimal
    metrics: dict[str, Any] = field(default_factory=dict)
    reasons: list[str] = field(default_factory=list)
    strategy_id: str = ""
    timestamp: str = ""


@dataclass(frozen=True, slots=True)
class SignalDTO:
    """Strategy signal passed to execution layer."""

    symbol: str
    exchange: str
    side: str
    signal_type: str
    confidence: Decimal
    quantity: int = 0
    price: Decimal | None = None
    entry_price: Decimal | None = None
    strategy: str = ""
    position_size_pct: Decimal = Decimal("0")
    metadata: dict[str, Any] | None = None

    @property
    def is_actionable(self) -> bool:
        return self.signal_type in (
            "BUY",
            "SELL",
            "STRONG_BUY",
            "STRONG_SELL",
            "ENTRY",
            "EXIT",
        ) and self.confidence > Decimal("0")

    def to_intent(
        self,
        risk_profile: "RiskProfile",
        account: "AccountView",
    ) -> "OrderIntent":
        """Convert this Signal into a risk-sized OrderIntent.

        This is the single, discoverable conversion step from "a strategy
        has an opinion" to "here is what to submit" — what didn't exist
        was a path that makes it structurally impossible to build an
        unsized-or-uncapped OrderIntent from a Signal by accident, because
        every conversion now passes through the caller's real RiskProfile
        and current Portfolio.

        Sizing is position-aware, not just signal-aware: the budget is
        ``capital * max_position_pct``, but the quantity computed is only
        the *remaining* room after subtracting whatever is already held in
        this symbol (via ``account.portfolio.symbol_exposure``). Without
        this, a strategy re-signaling on a symbol it already holds would
        size a *fresh* max-position order each time and silently pyramid
        past the intended limit — sizing from zero every time is the bug
        this method exists to make impossible, not just the missing sizing
        step itself.

        If this signal already carries an explicit ``quantity`` (a
        strategy's own sizing decision), it is treated as a ceiling, not a
        replacement: the final quantity is the smaller of the strategy's
        requested quantity and what ``risk_profile``/``account`` allow. If
        no quantity was set (the common case), the risk-computed remaining
        quantity is used directly.

        Raises
        ------
        ValueError
            If this signal is not actionable, if no usable price is
            available to size against (neither ``price`` nor
            ``entry_price`` set), or if there is no remaining room in this
            symbol (already at or past the position limit) — refuses to
            build a zero/negative-quantity OrderIntent rather than
            silently emitting one.
        """
        from domain.orders.intent import OrderIntent
        from domain.types import Side

        if not self.is_actionable:
            raise ValueError(
                f"Signal is not actionable (signal_type={self.signal_type!r}, "
                f"confidence={self.confidence})"
            )

        price = self.price if self.price is not None else self.entry_price
        if price is None or price <= 0:
            raise ValueError(
                "Signal has no usable price (price and entry_price both "
                "unset or non-positive) — cannot size an OrderIntent"
            )

        max_notional = risk_profile.capital * (risk_profile.max_position_pct / Decimal("100"))
        existing_notional = account.portfolio.symbol_exposure(self.symbol, self.exchange)
        remaining_notional = max(Decimal("0"), max_notional - existing_notional)
        risk_qty = int(remaining_notional / price) if price > 0 else 0

        quantity = min(self.quantity, risk_qty) if self.quantity > 0 else risk_qty
        if quantity <= 0:
            raise ValueError(
                f"No remaining position room for {self.symbol} — refusing to "
                "build a zero/negative-quantity OrderIntent (capital="
                f"{risk_profile.capital}, max_position_pct="
                f"{risk_profile.max_position_pct}, existing_notional="
                f"{existing_notional}, price={price})"
            )

        side = Side.BUY if self.side.upper() in ("BUY", "STRONG_BUY", "ENTRY") else Side.SELL

        return OrderIntent(
            symbol=self.symbol,
            exchange=self.exchange,
            side=side,
            quantity=quantity,
            price=price,
        )


__all__ = ["CandidateDTO", "SignalDTO"]
