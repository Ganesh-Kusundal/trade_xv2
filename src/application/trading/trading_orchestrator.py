"""TradingOrchestrator — connects Scanner→Strategy→OMS execution path.

The TradingOrchestrator is the missing link between the analytics layer
(scanner/strategy) and the execution layer (OMS/broker). It automates
the complete trading workflow:

1. Subscribe to CANDIDATE_GENERATED events from the EventBus
2. For each candidate, fetch features via FeatureFetcher
3. Run StrategyPipeline.evaluate_single(candidate, features)
4. Filter actionable signals (signal.is_actionable)
5. Convert signal to OmsOrderCommand
6. Place via ExecutionService or PlaceOrderUseCase (never bare OMS)
7. Publish RISK_APPROVED/RISK_REJECTED events based on OMS result
8. Publish SIGNAL_EXECUTED event with order_id

This orchestrator enables autonomous trading while maintaining
separation of concerns between analytics and execution.

Usage:
    orchestrator = TradingOrchestrator(
        event_bus=bus,
        order_manager=oms.order_manager,
        strategy_pipeline=strategy_pipeline,
        feature_fetcher=feature_fetcher,
        min_confidence=0.7,
        dry_run=False,
    )
    event_bus.subscribe(EventType.CANDIDATE_GENERATED, orchestrator.on_candidate)
    lifecycle_manager.register(orchestrator)
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import TYPE_CHECKING

from application.execution.execution_engine import ExecutionEngine
from application.oms.order_manager import OmsOrderCommand, OrderManager, OrderResult
from application.trading.candidate_evaluator import CandidateEvaluator
from application.trading.execution_planner import ExecutionPlanner
from application.trading.models import FeatureFetcher
from application.trading.order_placer import OrderPlacer
from domain import Order, OrderType, ProductType, Side
from domain.events.types import DomainEvent, EventType
from domain.models.trading import CandidateDTO, SignalDTO
from domain.orders.execution_plan import ExecutionPlan, SlicingAlgo
from domain.orders.requests import OrderRequest
from domain.ports import EventBusPort
from domain.ports.risk_manager import RiskManagerPort
from domain.ports.strategy_evaluator import StrategyEvaluator
from domain.ports.time_service import ClockPort, get_current_clock

if TYPE_CHECKING:
    from domain.lifecycle_health import HealthStatus

logger = logging.getLogger(__name__)


@dataclass
class OrchestratorConfig:
    """Configuration for the TradingOrchestrator.

    Attributes
    ----------
    min_confidence:
        Minimum confidence threshold for executing a signal (0.0-1.0).
        Signals below this threshold are logged but not executed.
    dry_run:
        If True, signals are evaluated but orders are NOT placed.
        Useful for paper trading and strategy validation.
    default_product_type:
        Default product type for orders (INTRADAY, DELIVERY, etc.).
    default_order_type:
        Default order type (MARKET, LIMIT, etc.).
    max_position_size_pct:
        Maximum position size as % of capital (0-100). 0 = no limit.
    feature_timeout_seconds:
        Timeout for feature fetching (seconds). None = no timeout.
    """

    min_confidence: float = 0.7
    dry_run: bool = False
    default_product_type: ProductType = ProductType.INTRADAY
    default_order_type: OrderType = OrderType.MARKET
    max_position_size_pct: float = 0.0
    feature_timeout_seconds: float | None = None
    default_exchange: str = "NSE"


class TradingOrchestrator:
    """Automated trading orchestrator connecting Scanner→Strategy→OMS.

    The orchestrator subscribes to CANDIDATE_GENERATED events, evaluates
    each candidate through the strategy pipeline, and executes actionable
    signals through the OMS.

    Internal decomposition
    ----------------------
    Heavy lifting is delegated to focused collaborators:

    - :class:`CandidateEvaluator` — feature fetching + strategy evaluation
    - :class:`ExecutionPlanner` — gating, plan building, command conversion
    - :class:`OrderPlacer` — equity resolution + OMS submission

    This class remains the **facade**: it owns the event-subscription
    lifecycle, counter management, and event publishing.

    Parameters
    ----------
    event_bus:
        EventBus for subscribing to candidate events and publishing
        execution events (SIGNAL_EXECUTED, RISK_APPROVED, RISK_REJECTED).
    order_manager:
        OrderManager for placing orders through the OMS.
    strategy_evaluator:
        StrategyEvaluator for evaluating candidates.
    feature_fetcher:
        FeatureFetcher for retrieving feature data for symbols.
    config:
        Optional configuration overrides.
    """

    def __init__(
        self,
        event_bus: EventBusPort,
        order_manager: OrderManager,
        strategy_evaluator: StrategyEvaluator,
        feature_fetcher: FeatureFetcher,
        config: OrchestratorConfig | None = None,
        submit_fn: Callable[[OmsOrderCommand], Order] | None = None,
        execution_engine: ExecutionEngine | None = None,
        order_command_fn: Callable[[OmsOrderCommand], OrderResult] | None = None,
        risk_manager: RiskManagerPort | None = None,
        clock: ClockPort | None = None,
    ) -> None:
        self._event_bus = event_bus
        self._order_manager = order_manager
        self._strategy_evaluator = strategy_evaluator
        self._feature_fetcher = feature_fetcher
        self._config = config or OrchestratorConfig()
        self._submit_fn = submit_fn
        self._execution_engine = execution_engine
        self._clock = clock or get_current_clock()
        # G7: kill-switch reads via the injected RiskManagerPort, never by
        # reaching into order_manager.risk_manager. Default to the order
        # manager's risk manager to stay backward-compatible with existing
        # wiring; pass risk_manager explicitly to decouple fully.
        self._risk_manager: RiskManagerPort | None = risk_manager or order_manager.risk_manager
        # ADR-012: when wired, signals flow through an injected order-command
        # function (built by the composition root from the CommandDispatcher) so
        # the orchestrator never imports or calls the OMS/broker directly.
        self._order_command_fn = order_command_fn

        # ── delegates ────────────────────────────────────────────────────
        self._evaluator = CandidateEvaluator(
            feature_fetcher=self._feature_fetcher,
            strategy_evaluator=self._strategy_evaluator,
            feature_timeout_seconds=self._config.feature_timeout_seconds,
        )
        self._order_placer = OrderPlacer(
            order_manager=self._order_manager,
            submit_fn=self._submit_fn,
            execution_engine=self._execution_engine,
            order_command_fn=self._order_command_fn,
            on_error=self._inc_error,
        )
        self._planner = ExecutionPlanner(
            min_confidence=self._config.min_confidence,
            dry_run=self._config.dry_run,
            default_order_type=self._config.default_order_type,
            default_product_type=self._config.default_product_type,
            default_exchange=self._config.default_exchange,
            max_position_size_pct=self._config.max_position_size_pct,
            kill_switch_check=self._is_kill_switch_active,
            resolve_equity=self._order_placer.resolve_equity,
        )

        self._executed_count: int = 0
        self._rejected_count: int = 0
        self._error_count: int = 0
        # P1-7 fix: Lock for thread-safe counter increments.
        self._counter_lock = threading.Lock()
        self._candidate_subscription_token: str | None = None
        self.name = "trading_orchestrator"

    # ── properties ───────────────────────────────────────────────────────

    @property
    def executed_count(self) -> int:
        """Number of signals successfully executed."""
        return self._executed_count

    @property
    def rejected_count(self) -> int:
        """Number of signals rejected (confidence filter, risk, etc.)."""
        return self._rejected_count

    @property
    def error_count(self) -> int:
        """Number of execution errors (feature fetch failure, OMS error, etc.)."""
        return self._error_count

    # ── event subscription ───────────────────────────────────────────────

    def attach_event_subscription(self) -> str:
        """Subscribe to CANDIDATE_GENERATED if not already subscribed."""
        if self._candidate_subscription_token is not None:
            return self._candidate_subscription_token
        self._candidate_subscription_token = self._event_bus.subscribe(
            EventType.CANDIDATE_GENERATED.value,
            self.on_candidate,
        )
        return self._candidate_subscription_token

    def detach_event_subscription(self) -> None:
        """Unsubscribe from CANDIDATE_GENERATED if this orchestrator owns the token."""
        if self._candidate_subscription_token is not None:
            self._event_bus.unsubscribe(self._candidate_subscription_token)
            self._candidate_subscription_token = None

    # ── main entry point ─────────────────────────────────────────────────

    def on_candidate(self, event: DomainEvent) -> None:
        """Handle CANDIDATE_GENERATED event.

        This is the main entry point for the orchestrator. It:
        1. Extracts candidate from event payload
        2. Fetches features for the symbol
        3. Evaluates candidate through strategy pipeline
        4. Filters actionable signals above confidence threshold
        5. Executes signals through OMS

        Parameters
        ----------
        event:
            CANDIDATE_GENERATED event with payload containing
            'symbol' and 'score' keys.
        """
        try:
            symbol = event.payload.get("symbol")
            score = event.payload.get("score", 0.0)
            correlation_id = (
                event.correlation_id
                or event.payload.get("candidate_id")
                or (f"{self.name}:{symbol}" if symbol else None)
            )

            if not symbol:
                logger.warning("CANDIDATE_GENERATED event missing symbol: %s", event)
                self._inc_error()
                return

            logger.info(
                "Orchestrator received candidate: symbol=%s, score=%.2f, correlation=%s",
                symbol,
                score,
                correlation_id,
            )

            # Create candidate object from event
            candidate = CandidateDTO(
                symbol=symbol,
                exchange=event.payload.get("exchange", self._config.default_exchange),
                score=Decimal(str(score)),
                reasons=[str(event.payload.get("reason", ""))],
                metrics={
                    k: Decimal(str(v))
                    for k, v in event.payload.items()
                    if k not in ("symbol", "score", "reason", "exchange")
                },
            )

            # Fetch features
            features = self._evaluator.fetch_features(symbol)
            if features is None:
                logger.warning("Feature fetch failed for %s, skipping execution", symbol)
                self._inc_error()
                return

            # Evaluate through strategy pipeline
            signals = self._evaluator.evaluate_candidate(candidate, features)

            # Execute actionable signals
            for signal in signals:
                self._execute_signal(signal, correlation_id)

        except Exception as exc:
            logger.exception("Orchestrator failed to process candidate event: %s", exc)
            self._inc_error()

    # ── signal execution (facade) ────────────────────────────────────────

    def _execute_signal(self, signal: SignalDTO, correlation_id: str) -> None:
        """Execute a single signal through the OMS.

        Delegates gating + plan building to :class:`ExecutionPlanner`,
        order placement to :class:`OrderPlacer`, and event publishing
        stays here.
        """
        result = self._planner.plan(signal, correlation_id)

        if result.rejected:
            self._inc_rejected()
            return
        if result.dry_run:
            self._inc_executed()
            return
        if not result.commands:
            return  # not actionable — no counter bump

        # Publish the plan-built event (post-gating) for observers/audit.
        if result.plan is not None:
            self._publish_plan_built(result.plan, signal)

        # Place each leg through the OMS and publish ORDER_REQUESTED.
        order_results = []
        for cmd in result.commands:
            order_result = self._order_placer.place(cmd, signal)
            self._publish_order_requested(cmd, result.plan, signal)
            order_results.append(order_result)

        if not order_results:
            self._inc_rejected()
            return

        # Publish execution events
        self._publish_execution_events(order_results, signal)

    # ── event publishing ─────────────────────────────────────────────────

    def _publish_execution_events(
        self,
        results: list[OrderResult],
        signal: SignalDTO,
    ) -> None:
        """Publish execution events (SIGNAL_EXECUTED, RISK_APPROVED, RISK_REJECTED).

        Parameters
        ----------
        results:
            Order placement results (one per plan leg).
        signal:
            Original signal that was executed.
        """
        for result in results:
            if result.success and result.order:
                self._inc_executed()

                self._event_bus.publish(
                    DomainEvent.now(
                        EventType.SIGNAL_EXECUTED.value,
                        payload={
                            "signal": signal,
                            "order_id": result.order.order_id,
                        },
                        symbol=signal.symbol,
                        source="TradingOrchestrator",
                        correlation_id=result.order.correlation_id,
                    )
                )

                self._event_bus.publish(
                    DomainEvent.now(
                        EventType.RISK_APPROVED.value,
                        payload={"order_id": result.order.order_id},
                        symbol=signal.symbol,
                        source="TradingOrchestrator",
                        correlation_id=result.order.correlation_id,
                    )
                )

                logger.info(
                    "Signal executed: %s %s -> order %s",
                    signal.symbol,
                    signal.signal_type,
                    result.order.order_id,
                )

            elif not result.success:
                self._inc_rejected()

                if result.error:
                    order_id = result.order.order_id if result.order else "unknown"
                    self._event_bus.publish(
                        DomainEvent.now(
                            EventType.RISK_REJECTED.value,
                            payload={
                                "order_id": order_id,
                                "rule": "risk_check",
                                "value": str(result.error),
                                "limit": "0",
                            },
                            symbol=signal.symbol,
                            source="TradingOrchestrator",
                        )
                    )

                logger.warning(
                    "Signal execution rejected: %s %s -> %s",
                    signal.symbol,
                    signal.signal_type,
                    result.error,
                )

    def _publish_plan_built(self, plan: ExecutionPlan, signal: SignalDTO) -> None:
        """Publish EXECUTION_PLAN_BUILT (post-gating, additive)."""
        self._event_bus.publish(
            DomainEvent.now(
                EventType.EXECUTION_PLAN_BUILT.value,
                payload={
                    "symbol": plan.symbol,
                    "strategy": plan.source_strategy,
                    "signal_type": plan.signal_type,
                    "legs_count": len(plan.legs),
                    "confidence": str(plan.confidence),
                    "total_qty": plan.sizing.total_qty,
                    "sizing_method": plan.sizing.method.value,
                    "slicing_algo": plan.slicing.algo.value,
                    "execution_plan": plan,
                },
                symbol=plan.symbol,
                source="TradingOrchestrator",
                correlation_id=plan.correlation_id,
            )
        )

    def _publish_order_requested(
        self,
        command: OmsOrderCommand,
        plan: ExecutionPlan | None,
        signal: SignalDTO,
    ) -> None:
        """Publish ORDER_REQUESTED with an algo-aware OrderRequest (additive)."""
        if plan is None:
            return
        try:
            request = OrderRequest(
                symbol=command.symbol,
                exchange=command.exchange,
                transaction_type=command.side,
                quantity=command.quantity,
                price=command.price,
                order_type=command.order_type,
                product_type=command.product_type,
                correlation_id=command.correlation_id,
                slice=plan.slicing.algo != SlicingAlgo.NONE,
                slice_count=plan.slicing.slice_count,
                slice_interval=plan.slicing.interval_seconds,
                twap_duration=plan.slicing.twap_duration_seconds,
                vwap_participation_rate=plan.slicing.vwap_participation_rate,
                slicing_algo=plan.slicing.algo.value,
                disclosed_quantity=plan.slicing.disclosed_qty,
            )
        except Exception as exc:  # pragma: no cover - defensive
            logger.debug("Skipping ORDER_REQUESTED publish: %s", exc)
            return
        self._event_bus.publish(
            DomainEvent.now(
                EventType.ORDER_REQUESTED.value,
                payload={
                    "symbol": request.symbol,
                    "request": request,
                    "slicing_algo": request.slicing_algo,
                },
                symbol=request.symbol,
                source="TradingOrchestrator",
                correlation_id=request.correlation_id,
            )
        )

    # ── kill switch ──────────────────────────────────────────────────────

    def _is_kill_switch_active(self) -> bool:
        """Check if kill switch is active.

        Delegates to the injected ``RiskManagerPort`` (G7). If no risk manager
        is configured, returns False (safe default).
        """
        if self._risk_manager is None:
            return False
        return self._risk_manager.is_kill_switch_active()

    # ── lifecycle ────────────────────────────────────────────────────────

    def health(self) -> HealthStatus:
        """ManagedService health snapshot."""

        from domain.lifecycle_health import HealthState, HealthStatus

        return HealthStatus(
            state=HealthState.HEALTHY,
            service=self.name,
            last_check=self._clock.now(),
            detail=(
                f"executed={self._executed_count} "
                f"rejected={self._rejected_count} "
                f"errors={self._error_count}"
            ),
        )

    def start(self) -> None:
        """Start the orchestrator.

        Called by LifecycleManager when the system starts.
        Subscribes to CANDIDATE_GENERATED unless the caller already
        attached a subscription via :meth:`attach_event_subscription`.
        """
        self.attach_event_subscription()
        logger.info(
            "TradingOrchestrator starting (dry_run=%s, min_confidence=%.2f)",
            self._config.dry_run,
            self._config.min_confidence,
        )

    def stop(self) -> None:
        """Stop the orchestrator.

        Called by LifecycleManager when the system shuts down.
        Unsubscribe from events and log final statistics.
        """
        self.detach_event_subscription()
        logger.info(
            "TradingOrchestrator stopping: executed=%d, rejected=%d, errors=%d",
            self._executed_count,
            self._rejected_count,
            self._error_count,
        )

    def reset_stats(self) -> None:
        """Reset execution statistics (thread-safe)."""
        with self._counter_lock:
            self._executed_count = 0
            self._rejected_count = 0
            self._error_count = 0

    # ── Thread-safe counter helpers (P1-7) ──────────────────────────────

    def _inc_executed(self) -> None:
        """Thread-safe increment of executed counter."""
        with self._counter_lock:
            self._executed_count += 1

    def _inc_rejected(self) -> None:
        """Thread-safe increment of rejected counter."""
        with self._counter_lock:
            self._rejected_count += 1

    def _inc_error(self) -> None:
        """Thread-safe increment of error counter."""
        with self._counter_lock:
            self._error_count += 1


__all__ = [
    "OrchestratorConfig",
    "TradingOrchestrator",
]
