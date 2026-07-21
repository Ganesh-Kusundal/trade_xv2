"""ExecutionPlan — domain aggregate formalizing signal→order conversion.

This aggregate replaces the previously-inline, duplicated signal→order
logic that lived inside ``TradingOrchestrator`` (``_signal_to_order_command``
+ ``_calculate_quantity``) and the parallel ``SignalDTO.to_intent`` path.

It is *pure*: no transport, application, or infrastructure imports. All
sizing math is delegated to :mod:`domain.orders.sizing`; all intent
construction reuses :class:`domain.orders.intent.OrderIntent`.

Design
------
A plan is built from a ``Signal``/``SignalDTO`` plus a :class:`PlanContext`
(the runtime inputs the planner needs — capital, position limits, routing
defaults, kill-switch state). The plan carries:

* ``source`` metadata (strategy, symbol, exchange, signal_type, confidence,
  correlation_id),
* ``legs`` — a list of :class:`OrderIntent` (multi-leg ready),
* ``sizing`` — total qty, per-leg allocation, and the method used
  (``PCT_EQUITY`` / ``ATR`` / ``FIXED``),
* ``slicing`` — the algo (``NONE`` / ``TWAP`` / ``VWAP`` / ``ICEBERG``) and
  its params (slice_count, interval, disclosed_qty, …),
* ``routing`` — order_type / product_type / exchange-segment / broker-algo,
* ``guards`` — min-confidence, kill-switch flag, validity window.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import TYPE_CHECKING, Any

from domain.enums import OrderType, ProductType, Side
from domain.market_enums import ExchangeId
from domain.orders.intent import OrderIntent
from domain.orders.sizing import (
    SizingMethod,
    compute_atr_quantity,
    compute_remaining_quantity,
)

if TYPE_CHECKING:
    from domain.models.trading import SignalDTO

_ACTIONABLE_BUYS = ("BUY", "STRONG_BUY", "ENTRY")


def _new_correlation_id() -> str:
    return f"plan:{uuid.uuid4().hex}"


class SlicingAlgo(str, Enum):
    """Order-slicing algorithm applied to the plan's aggregate quantity."""

    NONE = "NONE"
    TWAP = "TWAP"
    VWAP = "VWAP"
    ICEBERG = "ICEBERG"


@dataclass(frozen=True)
class OrderSizing:
    """Sizing decision for the whole plan (and per-leg allocation)."""

    total_qty: int
    per_leg_allocation: list[int] = field(default_factory=list)
    method: SizingMethod = SizingMethod.FIXED
    # Method parameters (only the relevant ones are populated).
    equity: Decimal = Decimal("0")
    max_position_pct: Decimal = Decimal("0")
    existing_notional: Decimal = Decimal("0")
    atr: Decimal | None = None
    atr_risk_pct: Decimal = Decimal("0")

    def __post_init__(self) -> None:
        if not self.per_leg_allocation:
            object.__setattr__(self, "per_leg_allocation", [self.total_qty])


@dataclass(frozen=True)
class SlicingPlan:
    """How the aggregate quantity is sliced into child orders."""

    algo: SlicingAlgo = SlicingAlgo.NONE
    slice_count: int = 1
    interval_seconds: int = 0
    disclosed_qty: int | None = None
    # Algo-specific parameters.
    twap_duration_seconds: int | None = None
    vwap_participation_rate: Decimal | None = None


@dataclass(frozen=True)
class RoutingHint:
    """Broker/routing hints carried on the plan (not transport fields)."""

    order_type: OrderType = OrderType.MARKET
    product_type: ProductType = ProductType.INTRADAY
    exchange_segment: str = ""
    broker_algo: str | None = None


@dataclass(frozen=True)
class PlanGuards:
    """Gate conditions that must hold for the plan to be executable."""

    min_confidence: Decimal = Decimal("0")
    kill_switch_active: bool = False
    validity_window_seconds: int | None = None


@dataclass(frozen=True)
class PlanContext:
    """Runtime inputs the planner needs (supplied by the application layer).

    The planner is pure — it never reaches into a risk manager or portfolio
    directly. The caller (orchestrator, ``SignalDTO.to_intent``) snapshots
    the live values into this context.
    """

    equity: Decimal = Decimal("0")
    max_position_pct: Decimal = Decimal("0")
    existing_notional: Decimal = Decimal("0")
    atr: Decimal | None = None
    atr_risk_pct: Decimal = Decimal("1")
    default_order_type: OrderType = OrderType.MARKET
    default_product_type: ProductType = ProductType.INTRADAY
    default_exchange: str = ExchangeId.NSE
    min_confidence: Decimal = Decimal("0")
    kill_switch_active: bool = False
    correlation_id: str | None = None
    strategy: str = ""
    # Slicing algorithm + params to apply when the plan is executed.
    slicing: SlicingPlan = field(default_factory=SlicingPlan)
    # When True an explicit ``signal.quantity`` is capped by the risk-computed
    # remaining room (the ``SignalDTO.to_intent`` policy). When False it is
    # treated as absolute (the orchestrator's legacy policy).
    cap_explicit_quantity: bool = False


@dataclass(frozen=True)
class ExecutionPlan:
    """Aggregate describing how a signal becomes one or more order intents."""

    source_strategy: str
    symbol: str
    exchange: str
    signal_type: str
    confidence: Decimal
    correlation_id: str | None
    legs: list[OrderIntent] = field(default_factory=list)
    sizing: OrderSizing = field(default_factory=OrderSizing)
    slicing: SlicingPlan = field(default_factory=SlicingPlan)
    routing: RoutingHint = field(default_factory=RoutingHint)
    guards: PlanGuards = field(default_factory=PlanGuards)

    # ── Construction ──────────────────────────────────────────────────

    @classmethod
    def from_signal(cls, signal: SignalDTO, ctx: PlanContext) -> ExecutionPlan:
        """Build a plan from a signal and a runtime context.

        Raises
        ------
        ValueError
            If the signal is not actionable, or if there is no usable price
            to size against (price and entry_price both unset/non-positive) —
            refusing to build an unsized plan by accident.
        """
        if not signal.is_actionable:
            raise ValueError(
                f"Signal is not actionable (signal_type={signal.signal_type!r}, "
                f"confidence={signal.confidence})"
            )

        price = signal.entry_price if signal.entry_price is not None else signal.price
        if price is None or price <= 0:
            raise ValueError(
                "Signal has no usable price (price and entry_price both unset "
                "or non-positive) — cannot size an OrderIntent"
            )

        side = Side.BUY if signal.signal_type in _ACTIONABLE_BUYS else Side.SELL
        sizing = cls._resolve_sizing(signal, ctx, price)

        routing = RoutingHint(
            order_type=ctx.default_order_type,
            product_type=ctx.default_product_type,
            exchange_segment=ctx.default_exchange,
        )
        guards = PlanGuards(
            min_confidence=ctx.min_confidence,
            kill_switch_active=ctx.kill_switch_active,
        )

        legs: list[OrderIntent] = []
        if sizing.total_qty > 0:
            base_cid = ctx.correlation_id
            if base_cid:
                leg_cid = f"{base_cid}:{ctx.strategy or signal.strategy or 'strategy'}"
            else:
                leg_cid = _new_correlation_id()
            legs.append(
                OrderIntent(
                    symbol=signal.symbol,
                    exchange=signal.exchange or ctx.default_exchange,
                    side=side,
                    quantity=sizing.total_qty,
                    price=price,
                    order_type=ctx.default_order_type,
                    product_type=ctx.default_product_type,
                    correlation_id=leg_cid,
                )
            )

        return cls(
            source_strategy=ctx.strategy or signal.strategy,
            symbol=signal.symbol,
            exchange=signal.exchange or ctx.default_exchange,
            signal_type=signal.signal_type,
            confidence=signal.confidence,
            correlation_id=ctx.correlation_id,
            legs=legs,
            sizing=sizing,
            slicing=ctx.slicing,
            routing=routing,
            guards=guards,
        )

    @staticmethod
    def _resolve_sizing(
        signal: SignalDTO,
        ctx: PlanContext,
        price: Decimal,
    ) -> OrderSizing:
        """Shared sizing math — used by both conversion paths.

        Mirrors the legacy ``TradingOrchestrator._calculate_quantity`` clamp
        (signal pct capped by config max) so existing behavior is preserved.
        """
        if signal.quantity and signal.quantity > 0:
            qty = int(signal.quantity)
            if ctx.cap_explicit_quantity:
                risk_qty = _pct_equity_qty(signal, ctx, price)
                qty = min(qty, risk_qty)
            return OrderSizing(
                total_qty=qty,
                per_leg_allocation=[qty],
                method=SizingMethod.FIXED,
            )

        pct = (
            signal.position_size_pct
            if (signal.position_size_pct and signal.position_size_pct > 0)
            else Decimal("0")
        )
        if ctx.max_position_pct and ctx.max_position_pct > 0:
            pct = min(pct, ctx.max_position_pct) if pct and pct > 0 else ctx.max_position_pct

        if pct and pct > 0 and price and price > 0:
            qty = compute_remaining_quantity(
                equity=ctx.equity,
                max_position_pct=pct,
                price=price,
                existing_notional=ctx.existing_notional,
            )
            return OrderSizing(
                total_qty=qty,
                per_leg_allocation=[qty],
                method=SizingMethod.PCT_EQUITY,
                equity=ctx.equity,
                max_position_pct=pct,
                existing_notional=ctx.existing_notional,
            )

        if ctx.atr and ctx.atr > 0 and price and price > 0:
            qty = compute_atr_quantity(
                equity=ctx.equity,
                atr=ctx.atr,
                risk_pct=ctx.atr_risk_pct,
                atr_multiplier=2,
            )
            return OrderSizing(
                total_qty=qty,
                per_leg_allocation=[qty],
                method=SizingMethod.ATR,
                atr=ctx.atr,
                atr_risk_pct=ctx.atr_risk_pct,
            )

        # No explicit size and nothing to size from — refuse a default qty
        # (ENG-003). Callers must set a quantity or sizing context.
        return OrderSizing(
            total_qty=0,
            per_leg_allocation=[0],
            method=SizingMethod.FIXED,
        )

    # ── Intents ───────────────────────────────────────────────────────

    def to_intents(self) -> list[OrderIntent]:
        """Return the plan's logical legs (one :class:`OrderIntent` each)."""
        return list(self.legs)

    def sliced_quantities(self) -> list[int]:
        """Deterministic per-slice quantity split for the slicing algo.

        ``NONE`` returns the single aggregate quantity. ``ICEBERG`` splits by
        ``disclosed_qty``. ``TWAP``/``VWAP`` split into ``slice_count`` chunks.
        Pure and clock-independent so it is safe under replay/tests.
        """
        total = self.sizing.total_qty
        algo = self.slicing.algo
        if total <= 0 or algo == SlicingAlgo.NONE:
            return [total]
        if algo == SlicingAlgo.ICEBERG and self.slicing.disclosed_qty:
            disc = max(1, self.slicing.disclosed_qty)
            n = (total + disc - 1) // disc
            if n <= 1:
                return [total]
            return [disc] * (n - 1) + [total - disc * (n - 1)]
        n = max(1, self.slicing.slice_count)
        base, rem = divmod(total, n)
        return [base + (1 if i < rem else 0) for i in range(n)]

    # ── Serialization (pure) ──────────────────────────────────────────

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_strategy": self.source_strategy,
            "symbol": self.symbol,
            "exchange": self.exchange,
            "signal_type": self.signal_type,
            "confidence": str(self.confidence),
            "correlation_id": self.correlation_id,
            "legs": [vars(leg) for leg in self.legs],
            "sizing": {
                "total_qty": self.sizing.total_qty,
                "per_leg_allocation": self.sizing.per_leg_allocation,
                "method": self.sizing.method.value,
            },
            "slicing": {
                "algo": self.slicing.algo.value,
                "slice_count": self.slicing.slice_count,
                "interval_seconds": self.slicing.interval_seconds,
                "disclosed_qty": self.slicing.disclosed_qty,
            },
        }


def _pct_equity_qty(signal: SignalDTO, ctx: PlanContext, price: Decimal) -> int:
    """Risk-computed remaining qty (used to cap explicit quantities)."""
    pct = (
        signal.position_size_pct
        if (signal.position_size_pct and signal.position_size_pct > 0)
        else ctx.max_position_pct
    )
    if not pct or pct <= 0 or not price or price <= 0:
        return 0
    return compute_remaining_quantity(
        equity=ctx.equity,
        max_position_pct=pct,
        price=price,
        existing_notional=ctx.existing_notional,
    )


__all__ = [
    "ExecutionPlan",
    "OrderSizing",
    "PlanContext",
    "PlanGuards",
    "RoutingHint",
    "SlicingAlgo",
    "SlicingPlan",
]
