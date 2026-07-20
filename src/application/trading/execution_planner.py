"""Execution planning — gating, plan building, and command conversion.

Extracted from ``TradingOrchestrator`` to separate signal gating and
order-command construction from event publishing and lifecycle concerns.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from application.oms.order_manager import OmsOrderCommand
from domain import OrderType, ProductType, Side
from domain.models.trading import SignalDTO
from domain.orders.execution_plan import ExecutionPlan, PlanContext
from domain.orders.placement import build_execution_plan, plan_to_intents

logger = logging.getLogger(__name__)


def _safe_decimal(value: object, default: str = "0") -> Decimal:
    """Best-effort Decimal conversion that never raises."""
    try:
        return Decimal(str(value))
    except (TypeError, ValueError, InvalidOperation):
        return Decimal(default)


@dataclass(frozen=True)
class PlanResult:
    """Result of execution planning.

    Attributes
    ----------
    commands:
        OmsOrderCommands ready for placement (empty when rejected / dry-run).
    plan:
        The :class:`ExecutionPlan` built during planning, or ``None`` when
        gating rejected the signal before plan construction.
    rejected:
        ``True`` when the signal was rejected (confidence, kill-switch, etc.).
    dry_run:
        ``True`` when the signal passed gating but dry-run mode is on.
    """

    commands: list[OmsOrderCommand]
    plan: ExecutionPlan | None = None
    rejected: bool = False
    dry_run: bool = False


class ExecutionPlanner:
    """Handles signal gating, plan building, and order-command conversion.

    Responsibilities
    ----------------
    - Signal actionability and confidence gating
    - Kill-switch check
    - Execution-plan building
    - Intent-to-OmsOrderCommand conversion

    Parameters
    ----------
    min_confidence:
        Minimum confidence for executing a signal (0.0–1.0).
    dry_run:
        When ``True``, signals are gated but no commands are produced.
    default_order_type:
        Default order type for plans.
    default_product_type:
        Default product type for plans.
    default_exchange:
        Default exchange segment.
    max_position_size_pct:
        Maximum position size as % of equity.  0 = no limit.
    kill_switch_check:
        Callable that returns ``True`` when the kill switch blocks orders.
    resolve_equity:
        Callable that returns the current available equity (float).
    """

    def __init__(
        self,
        min_confidence: float = 0.7,
        dry_run: bool = False,
        default_order_type: OrderType = OrderType.MARKET,
        default_product_type: ProductType = ProductType.INTRADAY,
        default_exchange: str = "NSE",
        max_position_size_pct: float = 0.0,
        kill_switch_check: Callable[[], bool] | None = None,
        resolve_equity: Callable[[], float] | None = None,
    ) -> None:
        self._min_confidence = min_confidence
        self._dry_run = dry_run
        self._default_order_type = default_order_type
        self._default_product_type = default_product_type
        self._default_exchange = default_exchange
        self._max_position_size_pct = max_position_size_pct
        self._kill_switch_check = kill_switch_check or (lambda: False)
        self._resolve_equity = resolve_equity or (lambda: 0.0)

    # ── plan context ─────────────────────────────────────────────────────

    def build_plan_context(
        self, signal: SignalDTO, correlation_id: str | None,
    ) -> PlanContext:
        """Snapshot the runtime inputs the planner needs."""
        base_cid = correlation_id or f"{signal.symbol}:{signal.strategy or 'strategy'}"
        return PlanContext(
            equity=_safe_decimal(self._resolve_equity()),
            max_position_pct=_safe_decimal(self._max_position_size_pct),
            existing_notional=Decimal("0"),
            atr=None,
            default_order_type=self._default_order_type,
            default_product_type=self._default_product_type,
            default_exchange=self._default_exchange,
            min_confidence=_safe_decimal(self._min_confidence),
            kill_switch_active=self._kill_switch_check(),
            correlation_id=base_cid,
            strategy=signal.strategy or "",
        )

    # ── main planning entry-point ────────────────────────────────────────

    def plan(self, signal: SignalDTO, correlation_id: str) -> PlanResult:
        """Build an execution plan from *signal*, returning commands or a
        rejection/dry-run status.

        The full gating pipeline runs here:
        1. Actionability check
        2. Confidence threshold
        3. Kill-switch
        4. Dry-run mode
        5. Plan construction + intent conversion
        """
        # 1 — actionability
        if not signal.is_actionable:
            logger.debug(
                "Signal not actionable: %s HOLD (confidence=%.2f)",
                signal.symbol,
                signal.confidence,
            )
            return PlanResult(commands=[])

        # 2 — confidence threshold
        if float(signal.confidence) < self._min_confidence:
            logger.info(
                "Signal below confidence threshold: %s %.2f < %.2f",
                signal.symbol,
                signal.confidence,
                self._min_confidence,
            )
            return PlanResult(commands=[], rejected=True)

        # 3 — dry-run
        if self._dry_run:
            logger.info(
                "DRY RUN: Would execute signal: %s %s (confidence=%.2f, entry=%.2f)",
                signal.symbol,
                signal.signal_type,
                float(signal.confidence),
                float(signal.entry_price or 0),
            )
            return PlanResult(commands=[], dry_run=True)

        # 5 — build plan
        try:
            ctx = self.build_plan_context(signal, correlation_id)
            execution_plan = build_execution_plan(signal, ctx)
        except ValueError as exc:
            logger.warning("Plan build failed for %s: %s", signal.symbol, exc)
            return PlanResult(commands=[], rejected=True)

        intents = plan_to_intents(execution_plan)
        if not intents:
            logger.warning(
                "Skipping signal for %s: plan produced no intents (refused qty)",
                signal.symbol,
            )
            return PlanResult(commands=[], plan=execution_plan, rejected=True)

        # 6 — convert to OmsOrderCommands
        commands = [
            self.intent_to_command(intent, signal)
            for intent in intents
            if intent.quantity > 0
        ]
        if not commands:
            return PlanResult(commands=[], plan=execution_plan, rejected=True)

        return PlanResult(commands=commands, plan=execution_plan)

    # ── quantity helper ──────────────────────────────────────────────────

    def calculate_quantity(self, signal: SignalDTO) -> int:
        """Resolve order quantity from explicit qty or position-size percent."""
        plan = build_execution_plan(signal, self.build_plan_context(signal, None))
        return plan.sizing.total_qty

    # ── command conversion ───────────────────────────────────────────────

    def signal_to_order_command(
        self,
        signal: SignalDTO,
        correlation_id: str,
    ) -> OmsOrderCommand:
        """Convert a :class:`SignalDTO` to an :class:`OmsOrderCommand`.

        Delegates to the shared :class:`ExecutionPlan` planner so the
        inline signal→order math lives in exactly one place.
        """
        plan = build_execution_plan(signal, self.build_plan_context(signal, correlation_id))
        intents = plan_to_intents(plan)
        if not intents:
            base_cid = correlation_id or f"{signal.symbol}:{signal.strategy or 'strategy'}"
            return OmsOrderCommand(
                symbol=signal.symbol,
                exchange=signal.exchange or self._default_exchange,
                side=Side.BUY if signal.signal_type in ("BUY", "STRONG_BUY") else Side.SELL,
                quantity=0,
                price=Decimal(str(signal.entry_price or signal.price or 0)),
                order_type=self._default_order_type,
                product_type=self._default_product_type,
                correlation_id=f"{base_cid}:{signal.strategy or 'strategy'}",
            )
        return self.intent_to_command(intents[0], signal)

    def intent_to_command(self, intent: object, signal: SignalDTO) -> OmsOrderCommand:
        """Bridge a domain :class:`OrderIntent` into an :class:`OmsOrderCommand`."""
        from application.oms.order_command_mapper import order_intent_to_oms_command

        return order_intent_to_oms_command(intent)
