"""TradingOrchestrator — connects Scanner→Strategy→OMS execution path.

The TradingOrchestrator is the missing link between the analytics layer
(scanner/strategy) and the execution layer (OMS/broker). It automates
the complete trading workflow:

1. Subscribe to CANDIDATE_GENERATED events from the EventBus
2. For each candidate, fetch features via FeatureFetcher
3. Run StrategyPipeline.evaluate_single(candidate, features)
4. Filter actionable signals (signal.is_actionable)
5. Convert signal to OmsOrderCommand
6. Call OrderManager.place_order() with the command
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
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

from application.execution.execution_service import ExecutionService
from application.oms.order_manager import OmsOrderCommand, OrderManager, OrderResult
from application.trading.models import (
    FeatureFetcher,
)
from domain import Order, OrderType, ProductType, Side
from domain.models.features import FeatureSet
from domain.models.trading import CandidateDTO, SignalDTO
from domain.ports.strategy_evaluator import StrategyEvaluator
from infrastructure.event_bus import (
    DomainEvent,
    EventBus,
    EventType,
)

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

    Parameters
    ----------
    event_bus:
        EventBus for subscribing to candidate events and publishing
        execution events (SIGNAL_EXECUTED, RISK_APPROVED, RISK_REJECTED).
    order_manager:
        OrderManager for placing orders through the OMS.
    strategy_pipeline:
        StrategyPipeline containing all active strategies.
    feature_fetcher:
        FeatureFetcher for retrieving feature data for symbols.
    config:
        Optional configuration overrides.

    Thread Safety
    -------------
    The orchestrator is thread-safe. Event handlers are executed
    sequentially by the EventBus (single dispatch worker).

    Event Publishing
    ----------------
    On successful execution:
    - SIGNAL_EXECUTED (signal, order_id)
    - RISK_APPROVED (order_id)

    On risk rejection:
    - RISK_REJECTED (order_id, rule, value, limit)
    - ORDER_REJECTED (existing OMS event)

    On execution failure:
    - Error logged, no event published (failure is transient)
    """

    def __init__(
        self,
        event_bus: EventBus,
        order_manager: OrderManager,
        strategy_evaluator: StrategyEvaluator,
        feature_fetcher: FeatureFetcher,
        config: OrchestratorConfig | None = None,
        submit_fn: Callable[[OmsOrderCommand], Order] | None = None,
        execution_service: ExecutionService | None = None,
    ) -> None:
        self._event_bus = event_bus
        self._order_manager = order_manager
        self._strategy_evaluator = strategy_evaluator
        self._feature_fetcher = feature_fetcher
        self._config = config or OrchestratorConfig()
        self._submit_fn = submit_fn
        self._execution_service = execution_service

        self._executed_count: int = 0
        self._rejected_count: int = 0
        self._error_count: int = 0
        self._candidate_subscription_token: str | None = None
        self.name = "trading_orchestrator"

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
            correlation_id = event.correlation_id

            if not symbol:
                logger.warning("CANDIDATE_GENERATED event missing symbol: %s", event)
                self._error_count += 1
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
            features = self._fetch_features(symbol)
            if features is None:
                logger.warning("Feature fetch failed for %s, skipping execution", symbol)
                self._error_count += 1
                return

            # Evaluate through strategy pipeline
            signals = self._evaluate_candidate(candidate, features)

            # Execute actionable signals
            for signal in signals:
                self._execute_signal(signal, correlation_id)

        except Exception as exc:
            logger.exception("Orchestrator failed to process candidate event: %s", exc)
            self._error_count += 1

    def _fetch_features(self, symbol: str) -> FeatureSet | None:
        """Fetch feature data for a symbol.

        Parameters
        ----------
        symbol:
            NSE/BSE symbol.

        Returns
        -------
        FeatureSet | None:
            Feature set or None if fetch failed.
        """
        try:
            if self._config.feature_timeout_seconds is not None:
                # Use concurrent.futures timeout wrapper for feature fetching
                import concurrent.futures

                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                    future = executor.submit(self._feature_fetcher.fetch, symbol)
                    return future.result(timeout=self._config.feature_timeout_seconds)
            else:
                return self._feature_fetcher.fetch(symbol)
        except Exception as exc:
            logger.exception("Feature fetch error for %s: %s", symbol, exc)
            return None

    def _evaluate_candidate(
        self,
        candidate: CandidateDTO,
        features: FeatureSet,
    ) -> list[SignalDTO]:
        """Evaluate candidate through strategy pipeline.

        Parameters
        ----------
        candidate:
            Candidate from scanner.
        features:
            Computed features for the symbol.

        Returns
        -------
        list[Signal]:
            List of signals from all strategies (may include HOLD signals).
        """
        try:
            signals = self._strategy_evaluator.evaluate_single(candidate, features)
            logger.info(
                "Evaluated %s: %d signals generated",
                candidate.symbol,
                len(signals),
            )
            return signals
        except Exception as exc:
            logger.exception(
                "Strategy evaluation failed for %s: %s",
                candidate.symbol,
                exc,
            )
            self._error_count += 1
            return []

    def _execute_signal(self, signal: SignalDTO, correlation_id: str) -> None:
        """Execute a single signal through the OMS.

        Parameters
        ----------
        signal:
            Actionable signal from strategy evaluation.
        correlation_id:
            Correlation ID for audit trail.
        """
        # Check if signal is actionable
        if not signal.is_actionable:
            logger.debug(
                "Signal not actionable: %s HOLD (confidence=%.2f)",
                signal.symbol,
                signal.confidence,
            )
            return

        # Check confidence threshold
        if float(signal.confidence) < self._config.min_confidence:
            logger.info(
                "Signal below confidence threshold: %s %.2f < %.2f",
                signal.symbol,
                signal.confidence,
                self._config.min_confidence,
            )
            self._rejected_count += 1
            return

        # Check kill switch
        if self._is_kill_switch_active():
            logger.warning("Kill switch active, blocking execution for %s", signal.symbol)
            self._rejected_count += 1
            return

        # Dry-run mode
        if self._config.dry_run:
            logger.info(
                "DRY RUN: Would execute signal: %s %s (confidence=%.2f, entry=%.2f)",
                signal.symbol,
                signal.signal_type,
                float(signal.confidence),
                float(signal.entry_price or 0),
            )
            self._executed_count += 1
            return

        # Convert signal to order command
        order_command = self._signal_to_order_command(signal, correlation_id)

        # Place order through OMS
        result = self._place_order(order_command, signal)

        # Publish execution events
        self._publish_execution_events(result, signal)

    def _signal_to_order_command(
        self,
        signal: SignalDTO,
        correlation_id: str,
    ) -> OmsOrderCommand:
        """Convert a SignalDTO to an OmsOrderCommand."""
        if signal.signal_type in ("BUY", "STRONG_BUY"):
            side = Side.BUY
        elif signal.signal_type in ("SELL", "STRONG_SELL"):
            side = Side.SELL
        else:
            raise ValueError(f"Cannot execute HOLD signal: {signal}")

        quantity = self._calculate_quantity(signal)
        entry = signal.entry_price or signal.price
        price = entry if entry is not None else Decimal("0")

        return OmsOrderCommand(
            symbol=signal.symbol,
            exchange=signal.exchange or self._config.default_exchange,
            side=side,
            quantity=quantity,
            price=price,
            order_type=self._config.default_order_type,
            product_type=self._config.default_product_type,
            correlation_id=f"{correlation_id}:{signal.strategy or 'strategy'}",
        )

    def _calculate_quantity(self, signal: SignalDTO) -> int:
        if signal.quantity > 0:
            return signal.quantity
        if signal.position_size_pct > Decimal("0"):
            return max(1, int(signal.position_size_pct))
        return 1

    def _place_order(
        self,
        command: OmsOrderCommand,
        signal: SignalDTO,
    ) -> OrderResult:
        """Place order through OMS.

        Parameters
        ----------
        command:
            Order command ready for placement.
        signal:
            Original signal for audit trail.

        Returns
        -------
        OrderResult:
            Result of order placement (success/failure).
        """
        try:
            logger.info(
                "Placing order: %s %s %d @ %.2f (correlation=%s)",
                command.side.value,
                command.symbol,
                command.quantity,
                float(command.price),
                command.correlation_id,
            )

            if self._execution_service is not None:
                result = self._execution_service.place_order(command)
            else:
                result = self._order_manager.place_order(
                    request=command,
                    submit_fn=self._submit_fn,
                )

            return result

        except Exception as exc:
            logger.exception(
                "Order placement failed for %s: %s",
                command.symbol,
                exc,
            )
            self._error_count += 1
            return OrderResult(success=False, error=str(exc))

    def _publish_execution_events(
        self,
        result: OrderResult,
        signal: SignalDTO,
    ) -> None:
        """Publish execution events (SIGNAL_EXECUTED, RISK_APPROVED, RISK_REJECTED).

        Parameters
        ----------
        result:
            Order placement result.
        signal:
            Original signal that was executed.
        """
        if result.success and result.order:
            self._executed_count += 1

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
            self._rejected_count += 1

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

    def _is_kill_switch_active(self) -> bool:
        """Check if kill switch is active.

        P4-5: Delegates to OrderManager risk manager for kill switch status.
        If no risk manager is configured, returns False (safe default).

        Returns
        -------
        bool:
            True if kill switch prevents order execution.
        """
        risk_manager = self._order_manager.risk_manager
        if risk_manager is None:
            return False
        return risk_manager.is_kill_switch_active()

    def health(self) -> HealthStatus:
        """ManagedService health snapshot."""

        from domain.lifecycle_health import HealthState, HealthStatus

        return HealthStatus(
            state=HealthState.HEALTHY,
            service=self.name,
            last_check=datetime.now(timezone.utc),
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
        """Reset execution statistics."""
        self._executed_count = 0
        self._rejected_count = 0
        self._error_count = 0


__all__ = [
    "OrchestratorConfig",
    "TradingOrchestrator",
]
