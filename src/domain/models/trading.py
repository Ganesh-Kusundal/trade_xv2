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
        risk_profile: RiskProfile,
        account: AccountView,
    ) -> OrderIntent:
        """Convert this Signal into a risk-sized OrderIntent.

        This is the single, discoverable conversion step from "a strategy
        has an opinion" to "here is what to submit". It now **delegates** to
        the shared :class:`~domain.orders.execution_plan.ExecutionPlan`
        planner (the same one ``TradingOrchestrator`` uses via
        ``build_execution_plan``), so the two previously-parallel signal→intent
        paths can no longer drift apart. The planner's ``cap_explicit_quantity``
        policy reproduces this method's original contract: an explicit
        ``quantity`` is a *ceiling*, capped by the risk-computed remaining
        room, never a fresh-from-zero max-position order.

        Sizing is position-aware: the budget is ``capital * max_position_pct``,
        and the quantity computed is only the *remaining* room after
        subtracting whatever is already held in this symbol (via
        ``account.portfolio.symbol_exposure``). Without this, a strategy
        re-signaling on a symbol it already holds would size a *fresh*
        max-position order each time and silently pyramid past the intended
        limit.

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
        from domain.orders.execution_plan import ExecutionPlan, PlanContext
        from domain.enums import OrderType, ProductType

        existing_notional = account.portfolio.symbol_exposure(self.symbol, self.exchange)
        ctx = PlanContext(
            equity=risk_profile.capital,
            max_position_pct=risk_profile.max_position_pct,
            existing_notional=existing_notional,
            default_order_type=OrderType.LIMIT,
            default_product_type=ProductType.INTRADAY,
            default_exchange=self.exchange,
            cap_explicit_quantity=True,
        )

        plan = ExecutionPlan.from_signal(self, ctx)
        if not plan.legs or plan.sizing.total_qty <= 0:
            raise ValueError(
                f"No remaining position room for {self.symbol} — refusing to "
                "build a zero/negative-quantity OrderIntent (capital="
                f"{risk_profile.capital}, max_position_pct="
                f"{risk_profile.max_position_pct}, existing_notional="
                f"{existing_notional}, price="
                f"{self.price if self.price is not None else self.entry_price})"
            )
        return plan.to_intents()[0]


__all__ = ["CandidateDTO", "SignalDTO"]
