"""TradingRuntimeFactory — single composition root for CLI, API, and scripts.

Unifies broker gateway wiring, OMS TradingContext, TradingOrchestrator,
optional BrokerInfrastructure for multi-broker routing, and runtime parity gating.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from domain.ports.broker_transport import BrokerTransport as MarketDataGateway
from infrastructure.lifecycle import LifecycleManager
from application.oms.context import TradingContext

if TYPE_CHECKING:
    from application.execution.execution_mode_adapter import ExecutionModeAdapter
    from application.trading.trading_orchestrator import TradingOrchestrator
    from infrastructure.broker_infrastructure import BrokerInfrastructure
    from infrastructure.event_bus.event_bus import EventBus

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
    extra: dict[str, Any] = field(default_factory=dict)


class TradingRuntimeFactory:
    """Build a :class:`Runtime` with consistent wiring across entry points."""

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

    @classmethod
    def build_for_api(
        cls,
        *,
        wire_orchestrator: bool = True,
        skip_parity_gate: bool = False,
        wire_intelligent_gateway: bool | None = None,
    ) -> Runtime:
        """API bootstrap: single AsyncEventBus shared with BrokerService + OMS."""
        from cli.services.broker_service import BrokerService
        from runtime.composition import create_api_event_bus

        event_bus, _ = create_api_event_bus(maxsize=2000)
        bs = BrokerService(event_bus=event_bus)
        factory = cls(
            wire_orchestrator=wire_orchestrator,
            skip_parity_gate=skip_parity_gate,
            wire_intelligent_gateway=wire_intelligent_gateway if wire_intelligent_gateway is not None else True,
        )
        return factory.build_from_broker_service(bs)

    def build(self) -> Runtime:
        """Construct and wire the full trading runtime (CLI path)."""
        from cli.services.broker_service import BrokerService

        bs = BrokerService()
        return self.build_from_broker_service(bs)

    def build_from_broker_service(self, bs: Any) -> Runtime:
        """Wire runtime from an existing :class:`BrokerService`."""
        from cli.services.oms_service import OmsService
        from runtime.parity_gate import assert_runtime_parity_or_raise
        from runtime.production_config import validate_production_config

        validate_production_config(surface="runtime")

        if not self._skip_parity_gate:
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
        gateway = bs._gateway if bs._active_name == "dhan" else bs._upstox_gateway

        event_bus = getattr(bs, "_event_bus", None)
        if event_bus is None and tc is not None:
            event_bus = tc.event_bus

        broker_infrastructure = None
        if self._wire_intelligent_gateway or self._both_brokers_available(bs):
            broker_infrastructure = self._build_broker_infrastructure(bs)

        orchestrator = None
        if self._wire_orchestrator and tc is not None:
            orchestrator = self._wire_trading_orchestrator(tc, gateway, bs.lifecycle)

        execution_adapter = None
        # Note: "live" mode is handled directly in ExecutionService,
        # no adapter needed. Only paper/replay/backtest need adapters.
        # See application/execution/execution_mode_adapter.py docstring.

        oms_service = OmsService(
            gateway=gateway,
            trading_context=tc,
        )

        return Runtime(
            broker_name=bs.active_broker_name,
            gateway=gateway,
            trading_context=tc,
            lifecycle=bs.lifecycle,
            oms_service=oms_service,
            http_observability=bs.http_observability,
            readiness_report=getattr(bs, "_readiness_report", None),
            live_actionable=bs.live_actionable,
            trading_orchestrator=orchestrator,
            broker_infrastructure=broker_infrastructure,
            broker_service=bs,
            event_bus=event_bus,
            execution_adapter=execution_adapter,
        )

    @staticmethod
    def _both_brokers_available(broker_service: Any) -> bool:
        dhan_gw = getattr(broker_service, "_gateway", None)
        upstox_gw = getattr(broker_service, "_upstox_gateway", None)
        return dhan_gw is not None and upstox_gw is not None

    def _wire_trading_orchestrator(
        self,
        tc: TradingContext,
        gateway: MarketDataGateway | None,
        lifecycle: LifecycleManager,
    ) -> Any:
        from application.trading.multi_strategy_runtime import MultiStrategyRuntime
        from analytics.pipeline.features import ATR, RSI, SMA
        from analytics.pipeline.pipeline import FeaturePipeline
        from infrastructure.event_bus import EventType
        from application.trading.feature_fetcher import PipelineFeatureFetcher
        from application.trading.trading_orchestrator import (
            OrchestratorConfig,
            TradingOrchestrator,
        )

        pipeline = FeaturePipeline().add(RSI(14)).add(ATR(14)).add(SMA(20))
        multi = MultiStrategyRuntime()
        strategy_pipeline = multi.pipeline
        feature_fetcher = PipelineFeatureFetcher(pipeline=pipeline, gateway=gateway)

        config = OrchestratorConfig(
            min_confidence=float(os.getenv("ORCHESTRATOR_MIN_CONFIDENCE", "0.7")),
            dry_run=self._orchestrator_dry_run,
        )
        orchestrator = TradingOrchestrator(
            event_bus=tc.event_bus,
            order_manager=tc.order_manager,
            strategy_evaluator=strategy_pipeline,
            feature_fetcher=feature_fetcher,
            config=config,
        )
        tc.event_bus.subscribe(EventType.CANDIDATE_GENERATED, orchestrator.on_candidate)
        lifecycle.register(orchestrator)
        logger.info(
            "TradingOrchestrator wired (dry_run=%s)",
            config.dry_run,
        )
        return orchestrator

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
        from infrastructure.bootstrap import bootstrap_from_gateways, policy_from_env

        dhan_gw = getattr(broker_service, "_gateway", None)
        upstox_gw = getattr(broker_service, "_upstox_gateway", None)
        gateway_pairs = []
        if dhan_gw is not None:
            gateway_pairs.append(("dhan", dhan_gw))
        if upstox_gw is not None:
            gateway_pairs.append(("upstox", upstox_gw))
        if len(gateway_pairs) < 2:
            logger.info("BrokerInfrastructure skipped: fewer than 2 brokers configured")
            return None
        try:
            infra = asyncio.run(
                bootstrap_from_gateways(gateway_pairs, policy=policy_from_env())
            )
            logger.info("BrokerInfrastructure wired for multi-broker routing")
            return infra
        except Exception as exc:
            logger.warning("Failed to build BrokerInfrastructure: %s", exc)
            return None


def build_runtime(
    broker: str = "dhan",
    *,
    authorize_risk_fail_open: bool = False,
    env_path: Path | None = None,
    wire_orchestrator: bool = True,
    wire_intelligent_gateway: bool | None = None,
    skip_parity_gate: bool = False,
) -> Runtime:
    """Convenience wrapper around :class:`TradingRuntimeFactory`."""
    return TradingRuntimeFactory(
        broker=broker,
        authorize_risk_fail_open=authorize_risk_fail_open,
        env_path=env_path,
        wire_orchestrator=wire_orchestrator,
        wire_intelligent_gateway=wire_intelligent_gateway,
        skip_parity_gate=skip_parity_gate,
    ).build()
