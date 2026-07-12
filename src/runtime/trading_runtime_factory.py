"""TradingRuntimeFactory — wire a Runtime from an existing broker service.

BrokerService construction (CLI/API) lives in the UI compose composition root.
This package wires only an already-built broker service; it must not depend on
the presentation layer.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from application.oms.context import TradingContext
from application.oms.order_manager import OrderResult
from domain.ports.broker_transport import BrokerTransport as MarketDataGateway
from infrastructure.lifecycle import LifecycleManager

if TYPE_CHECKING:
    from application.execution.execution_mode_adapter import ExecutionModeAdapter
    from application.trading.trading_orchestrator import TradingOrchestrator
    from infrastructure.broker_infrastructure import BrokerInfrastructure
    from infrastructure.event_bus.event_bus import EventBus
    from runtime.resilience import ResilienceConfig

logger = logging.getLogger(__name__)


@dataclass
class Runtime:
    """Fully-wired trading runtime."""

    broker_name: str
    gateway: MarketDataGateway | None
    trading_context: TradingContext | None
    lifecycle: LifecycleManager
    oms_service: Any
    http_observability: Any
    readiness_report: dict[str, Any] | None
    live_actionable: bool
    trading_orchestrator: TradingOrchestrator | None = None
    broker_infrastructure: BrokerInfrastructure | None = None
    broker_service: Any | None = None
    event_bus: EventBus | None = None
    execution_adapter: ExecutionModeAdapter | None = None
    resilience: ResilienceConfig | None = None
    pattern_engine: Any | None = None
    extra: dict[str, Any] = field(default_factory=dict)


class TradingRuntimeFactory:
    """Build a :class:`Runtime` from an injected broker service."""

    def __init__(
        self,
        *,
        broker: str = "dhan",
        authorize_risk_fail_open: bool = False,
        env_path: Path | None = None,
        wire_orchestrator: bool = True,
        wire_intelligent_gateway: bool | None = None,
        orchestrator_dry_run: bool | None = None,
        skip_parity_gate: bool = False,
        resilience: ResilienceConfig | None = None,
    ) -> None:
        self._broker = broker
        self._authorize_risk_fail_open = authorize_risk_fail_open
        self._env_path = env_path
        self._wire_orchestrator = wire_orchestrator
        if wire_intelligent_gateway is None:
            wire_intelligent_gateway = os.getenv("ENABLE_INTELLIGENT_GATEWAY", "0") == "1"
        self._wire_intelligent_gateway = wire_intelligent_gateway
        if orchestrator_dry_run is None:
            orchestrator_dry_run = os.getenv("ORCHESTRATOR_DRY_RUN", "1") == "1"
        self._orchestrator_dry_run = orchestrator_dry_run
        self._skip_parity_gate = skip_parity_gate
        # ADR-012 appendix: resilience subsystem is a visible kernel dependency.
        from runtime.resilience import ResilienceConfig

        self._resilience = resilience or ResilienceConfig.from_env()

    def build_from_broker_service(self, bs: Any) -> Runtime:
        """Wire runtime from an existing :class:`BrokerService`."""
        from runtime.parity_gate import assert_runtime_parity_or_raise
        from runtime.production_config import validate_production_config

        validate_production_config(surface="runtime")

        if not self._skip_parity_gate and self._resilience.parity_gate_enabled:
            assert_runtime_parity_or_raise()

        if self._authorize_risk_fail_open:
            if os.environ.get("TRADEX_AUTHORIZE_RISK_FAIL_OPEN") != "1":
                raise RuntimeError(
                    "authorize_risk_fail_open=True requires "
                    "TRADEX_AUTHORIZE_RISK_FAIL_OPEN=1 in the environment"
                )
            os.environ["RISK_FAIL_OPEN"] = "1"

        _ = bs.active_broker  # force init

        tc = bs.trading_context
        # G1 (P5-1): select the active gateway via the BrokerService property
        # instead of a private-attribute string branch. No `_active_name`
        # comparison remains — the active broker is resolved in one place.
        gateway = bs.active_broker

        event_bus = getattr(bs, "_event_bus", None)
        if event_bus is None and tc is not None:
            event_bus = tc.event_bus

        broker_infrastructure = None
        if self._wire_intelligent_gateway or self._both_brokers_available(bs):
            broker_infrastructure = self._build_broker_infrastructure(bs)

        orchestrator = None
        pattern_engine = None
        if self._wire_orchestrator and tc is not None:
            orchestrator, pattern_engine = self._wire_trading_orchestrator(
                tc, gateway, bs.lifecycle
            )

        execution_adapter = None
        # Note: "live" mode is handled directly in ExecutionService,
        # no adapter needed. Only paper/replay/backtest need adapters.
        # See application/execution/execution_mode_adapter.py docstring.

        # D6: OmsService retired — BrokerService owns order place/cancel + live_actionable.
        return Runtime(
            broker_name=bs.active_broker_name,
            gateway=gateway,
            trading_context=tc,
            lifecycle=bs.lifecycle,
            oms_service=bs,
            http_observability=bs.http_observability,
            readiness_report=getattr(bs, "_readiness_report", None),
            live_actionable=bs.live_actionable,
            trading_orchestrator=orchestrator,
            broker_infrastructure=broker_infrastructure,
            broker_service=bs,
            event_bus=event_bus,
            execution_adapter=execution_adapter,
            resilience=self._resilience,
            pattern_engine=pattern_engine,
        )

    @staticmethod
    def _both_brokers_available(broker_service: Any) -> bool:
        # Select by broker_id through the public gateways seam, not
        # private-attr string access (G1 pattern).
        gateways = broker_service.gateways
        return gateways.get("dhan") is not None and gateways.get("upstox") is not None

    def _wire_trading_orchestrator(
        self,
        tc: TradingContext,
        gateway: MarketDataGateway | None,
        lifecycle: LifecycleManager,
    ) -> Any:
        from analytics.pipeline.features import ATR, RSI, SMA, CandlestickPattern
        from analytics.pipeline.pipeline import FeaturePipeline
        from analytics.strategy.pipeline import StrategyPipeline
        from application.trading.feature_fetcher import PipelineFeatureFetcher
        from application.trading.multi_strategy_runtime import MultiStrategyRuntime
        from application.trading.trading_orchestrator import (
            OrchestratorConfig,
            TradingOrchestrator,
        )
        from infrastructure.event_bus import EventType

        # Core feature pipeline now also surfaces candlestick/swing patterns so
        # they feed both scanners and strategies (Tier 1-C pattern engine).
        pipeline = (
            FeaturePipeline()
            .add(RSI(14))
            .add(ATR(14))
            .add(SMA(20))
            .add(CandlestickPattern())
        )

        # Build the strategy pipeline: keep all discovered built-in strategies
        # and append the pattern-driven strategy so patterns can drive signals.
        multi = MultiStrategyRuntime()
        from analytics.scanner.patterns import PatternEngine, PatternStrategy

        strategy_instances = [*multi.pipeline.strategies, PatternStrategy()]
        strategy_pipeline = StrategyPipeline(strategies=strategy_instances)

        # Standalone pattern engine for direct pattern scanning.
        pattern_engine = PatternEngine()

        feature_fetcher = PipelineFeatureFetcher(pipeline=pipeline, gateway=gateway)

        config = OrchestratorConfig(
            min_confidence=float(os.getenv("ORCHESTRATOR_MIN_CONFIDENCE", "0.7")),
            dry_run=self._orchestrator_dry_run,
        )
        # ADR-012: route signals through a CommandDispatcher so the orchestrator
        # never calls the OMS/broker directly. Built here (runtime layer) wrapping
        # the context's OrderManager; the critical path stays synchronous. The
        # orchestrator receives a closure (order_command_fn) so it does not import
        # runtime.commands itself (keeps application -> runtime cycle-free).
        from runtime.commands import CommandDispatcher, OrderCommandHandler, PlaceOrderCommand

        command_dispatcher = CommandDispatcher(event_bus=tc.event_bus)
        command_dispatcher.register_handler(OrderCommandHandler(tc.order_manager))

        def order_command_fn(oms_cmd: Any) -> Any:
            cmd = PlaceOrderCommand(
                correlation_id=oms_cmd.correlation_id,
                symbol=oms_cmd.symbol,
                exchange=oms_cmd.exchange,
                side=oms_cmd.side,
                quantity=oms_cmd.quantity,
                price=oms_cmd.price,
                order_type=oms_cmd.order_type,
                product_type=oms_cmd.product_type,
            )
            result = command_dispatcher.dispatch(cmd)
            return OrderResult(
                success=result.success,
                order=result.data,
                error=result.error or "",
            )

        orchestrator = TradingOrchestrator(
            event_bus=tc.event_bus,
            order_manager=tc.order_manager,
            strategy_evaluator=strategy_pipeline,
            feature_fetcher=feature_fetcher,
            config=config,
            order_command_fn=order_command_fn,
        )
        tc.event_bus.subscribe(EventType.CANDIDATE_GENERATED, orchestrator.on_candidate)
        lifecycle.register(orchestrator)
        logger.info(
            "TradingOrchestrator wired (dry_run=%s)",
            config.dry_run,
        )
        return orchestrator, pattern_engine

    def _build_broker_infrastructure(
        self,
        broker_service: Any,
    ) -> Any | None:
        """Build BrokerInfrastructure from available broker gateways.

        Uses ``bootstrap_from_gateways`` to create a fully-wired
        ``BrokerInfrastructure`` with ``BrokerRouter``, ``HistoricalDataCoordinator``,
        ``QuotaScheduler``, and ``StreamOrchestrator``.
        """
        import asyncio

        from domain.policies.source_selection import auto_dual_broker_policy
        from runtime.broker_infrastructure import build_infrastructure

        # Select by broker_id through the public gateways seam, not
        # private-attr string access (G1 pattern).
        gateways = broker_service.gateways
        gateway_pairs: list[tuple[str, Any]] = []
        if gateways.get("dhan") is not None:
            gateway_pairs.append(("dhan", gateways["dhan"]))
        if gateways.get("upstox") is not None:
            gateway_pairs.append(("upstox", gateways["upstox"]))
        if len(gateway_pairs) < 2:
            logger.info("BrokerInfrastructure skipped: fewer than 2 brokers configured")
            return None
        execution_account = gateway_pairs[0][0]
        try:
            infra = asyncio.run(
                build_infrastructure(
                    gateways=[gw for _, gw in gateway_pairs],
                    policy=auto_dual_broker_policy(execution_account=execution_account),
                )
            )
            logger.info("BrokerInfrastructure wired for multi-broker routing")
            return infra
        except Exception as exc:
            logger.warning("Failed to build BrokerInfrastructure: %s", exc)
            return None
