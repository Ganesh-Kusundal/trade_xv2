"""Single composition root (ADR-017).

All runtime wiring lives here.  ``TradingRuntimeFactory`` in
``trading_runtime_factory.py`` is a deprecated re-export kept for backward
compatibility until all call sites migrate.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from application.oms.context import TradingContext
from domain.ports.broker_transport import BrokerTransport as MarketDataGateway
from infrastructure.lifecycle import LifecycleManager

if TYPE_CHECKING:
    from application.trading.trading_orchestrator import TradingOrchestrator
    from infrastructure.broker_infrastructure import BrokerInfrastructure
    from infrastructure.event_bus.event_bus import EventBus
    from runtime.resilience import ResilienceConfig

logger = logging.getLogger(__name__)

RuntimeMode = Literal["trade", "market", "sim"]


# ---------------------------------------------------------------------------
# Runtime dataclass — the output type of the composition root.
# ---------------------------------------------------------------------------


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
    resilience: ResilienceConfig | None = None
    pattern_engine: Any | None = None
    extra: dict[str, Any] = field(default_factory=dict)
    _streams_started: bool = field(default=False, init=False, repr=False)

    async def start(self) -> None:
        """Start deferred broker stream orchestration (safe under a running loop)."""
        if self._streams_started:
            return
        infra = self.broker_infrastructure
        if infra is not None:
            await infra.streams.start()
        self._streams_started = True


# ---------------------------------------------------------------------------
# Build options
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BuildOptions:
    """Options for :func:`build`."""

    broker: str = "dhan"
    mode: RuntimeMode = "trade"
    authorize_risk_fail_open: bool = False
    env_path: Path | None = None
    wire_orchestrator: bool = True
    wire_intelligent_gateway: bool | None = None
    orchestrator_dry_run: bool | None = None
    skip_parity_gate: bool = False
    resilience: Any | None = None
    extra: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Private wiring helpers (extracted from TradingRuntimeFactory)
# ---------------------------------------------------------------------------


def _both_brokers_available(broker_service: Any) -> bool:
    gateways = broker_service.gateways
    return gateways.get("dhan") is not None and gateways.get("upstox") is not None


def _wire_trading_orchestrator(
    tc: TradingContext,
    gateway: MarketDataGateway | None,
    lifecycle: LifecycleManager,
    *,
    orchestrator_dry_run: bool = True,
) -> Any:
    from analytics.pipeline.features import ATR, RSI, SMA, CandlestickPattern
    from analytics.pipeline.pipeline import FeaturePipeline
    from analytics.scanner.patterns import PatternEngine, PatternStrategy
    from analytics.strategy.pipeline import StrategyPipeline
    from application.trading.feature_fetcher import PipelineFeatureFetcher
    from application.trading.multi_strategy_runtime import MultiStrategyRuntime
    from application.trading.trading_orchestrator import (
        OrchestratorConfig,
        TradingOrchestrator,
    )
    from infrastructure.event_bus import EventType
    from runtime.commands import build_order_dispatcher

    pipeline = (
        FeaturePipeline()
        .add(RSI(14))
        .add(ATR(14))
        .add(SMA(20))
        .add(CandlestickPattern())
    )

    multi = MultiStrategyRuntime()
    strategy_instances = [*multi.pipeline.strategies, PatternStrategy()]
    strategy_pipeline = StrategyPipeline(strategies=strategy_instances)

    pattern_engine = PatternEngine()
    feature_fetcher = PipelineFeatureFetcher(pipeline=pipeline, gateway=gateway)

    config = OrchestratorConfig(
        min_confidence=float(os.getenv("ORCHESTRATOR_MIN_CONFIDENCE", "0.7")),
        dry_run=orchestrator_dry_run,
    )

    order_command_fn = build_order_dispatcher(
        tc.order_manager,
        event_bus=tc.event_bus,
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
    broker_service: Any,
) -> Any | None:
    """Build BrokerInfrastructure from available broker gateways."""
    from domain.policies.source_selection import auto_dual_broker_policy
    from runtime.broker_infrastructure import build_infrastructure

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
        infra = build_infrastructure(
            gateways=[gw for _, gw in gateway_pairs],
            policy=auto_dual_broker_policy(execution_account=execution_account),
        )
        logger.info("BrokerInfrastructure wired for multi-broker routing")
        return infra
    except Exception as exc:
        logger.warning("Failed to build BrokerInfrastructure: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_from_broker_service(
    broker_service: Any,
    *,
    options: BuildOptions | None = None,
) -> Runtime:
    """Build a :class:`Runtime` from an injected broker service (canonical API)."""
    from runtime.composition import wire_domain_port_sinks
    from runtime.parity_gate import assert_runtime_parity_or_raise
    from runtime.production_config import is_production_environment, validate_production_config

    opts = options or BuildOptions()

    wire_domain_port_sinks()
    validate_production_config(surface="runtime")

    # ADR-012 appendix: resilience subsystem is a visible kernel dependency.
    from runtime.resilience import ResilienceConfig

    resilience = opts.resilience or ResilienceConfig.from_env()

    if opts.skip_parity_gate and is_production_environment():
        raise RuntimeError(
            "skip_parity_gate=True is forbidden in production "
            "(quant parity must pass before live boot)"
        )

    if not opts.skip_parity_gate and resilience.parity_gate_enabled:
        assert_runtime_parity_or_raise()

    if opts.authorize_risk_fail_open:
        if os.environ.get("TRADEX_AUTHORIZE_RISK_FAIL_OPEN") != "1":
            raise RuntimeError(
                "authorize_risk_fail_open=True requires "
                "TRADEX_AUTHORIZE_RISK_FAIL_OPEN=1 in the environment"
            )
        os.environ["RISK_FAIL_OPEN"] = "1"

    _ = broker_service.active_broker  # force init

    tc = broker_service.trading_context
    gateway = broker_service.active_broker

    event_bus = getattr(broker_service, "_event_bus", None)
    if event_bus is None and tc is not None:
        event_bus = tc.event_bus

    wire_intelligent_gateway = opts.wire_intelligent_gateway
    if wire_intelligent_gateway is None:
        wire_intelligent_gateway = os.getenv("ENABLE_INTELLIGENT_GATEWAY", "0") == "1"

    broker_infrastructure = None
    if wire_intelligent_gateway or _both_brokers_available(broker_service):
        broker_infrastructure = _build_broker_infrastructure(broker_service)

    orchestrator = None
    pattern_engine = None
    orchestrator_dry_run = opts.orchestrator_dry_run
    if orchestrator_dry_run is None:
        orchestrator_dry_run = os.getenv("ORCHESTRATOR_DRY_RUN", "1") == "1"

    if opts.wire_orchestrator and tc is not None:
        orchestrator, pattern_engine = _wire_trading_orchestrator(
            tc, gateway, broker_service.lifecycle,
            orchestrator_dry_run=orchestrator_dry_run,
        )

    runtime = Runtime(
        broker_name=broker_service.active_broker_name,
        gateway=gateway,
        trading_context=tc,
        lifecycle=broker_service.lifecycle,
        oms_service=broker_service,
        http_observability=broker_service.http_observability,
        readiness_report=getattr(broker_service, "_readiness_report", None),
        live_actionable=broker_service.live_actionable,
        trading_orchestrator=orchestrator,
        broker_infrastructure=broker_infrastructure,
        broker_service=broker_service,
        event_bus=event_bus,
        resilience=resilience,
        pattern_engine=pattern_engine,
    )
    if opts.extra:
        runtime.extra.update(opts.extra)
    return runtime


def build(
    broker_service: Any,
    *,
    mode: RuntimeMode = "trade",
    broker: str | None = None,
    skip_parity_gate: bool | None = None,
    **kwargs: Any,
) -> Runtime:
    """Unified composition entry (ADR-017).

    Args:
        broker_service: Wired ``BrokerService`` from UI compose / API bootstrap.
        mode: Session mode hint stored on ``runtime.extra`` for callers.
        broker: Broker id override (defaults from service when omitted).
        skip_parity_gate: Override parity gate (defaults from env).
        **kwargs: Forwarded to :class:`BuildOptions` fields.
    """
    if broker_service is None:
        raise ValueError("broker_service is required for runtime.factory.build")
    if skip_parity_gate is None:
        skip_parity_gate = os.getenv("SKIP_PARITY_GATE", "0") == "1"
    broker_id = broker or broker_service.active_broker_name or "dhan"
    opts = BuildOptions(
        broker=str(broker_id),
        mode=mode,
        skip_parity_gate=skip_parity_gate,
        **{k: v for k, v in kwargs.items() if k in BuildOptions.__dataclass_fields__},
    )
    runtime = build_from_broker_service(broker_service, options=opts)
    runtime.extra.setdefault("mode", mode)
    return runtime
