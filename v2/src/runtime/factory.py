"""RuntimeFactory — assemble Runtime from AppConfig (composition root)."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from application.execution.execution_engine import ExecutionEngine
from application.oms.order_manager import OrderManager
from application.oms.position_manager import PositionManager
from application.oms.trading_cache import TradingCache
from application.risk.risk_manager import RiskManager
from application.risk.rules import (
    DailyLossRule,
    OrderRateRule,
    OrderSizeRule,
    PositionLimitRule,
)
from config.schema import AppConfig, Environment, RiskConfig
from domain.value_objects import CorrelationId
from infrastructure.component.lifecycle import LifecycleManager
from infrastructure.idempotency import IdempotencyGuard, IdempotencyStatus
from infrastructure.message_bus import InMemoryMessageLog, MessageBus
from infrastructure.observability.audit import AuditSink
from runtime.execution_target import resolve_clock, resolve_fill_source
from runtime.runtime import Runtime


class _EngineIdempotency:
    """Adapt IdempotencyGuard → ExecutionEngine (None for NEW, prior for DUPLICATE)."""

    def __init__(self, guard: IdempotencyGuard) -> None:
        self._guard = guard

    def check_and_reserve(self, correlation_id: CorrelationId) -> Any:
        result = self._guard.check_and_reserve(correlation_id)
        if result.status is IdempotencyStatus.DUPLICATE:
            return result.prior_result
        return None

    def record_result(self, correlation_id: CorrelationId, result: Any) -> None:
        self._guard.record_result(correlation_id, result)


def _risk_from_config(cfg: RiskConfig) -> RiskManager:
    return RiskManager(
        rules=[
            OrderSizeRule(max_qty=Decimal(cfg.max_order_size)),
            PositionLimitRule(max_qty=Decimal(cfg.max_position_size)),
            DailyLossRule(max_loss=Decimal(str(cfg.max_daily_loss))),
            OrderRateRule(max_orders=cfg.max_orders_per_day),
        ]
    )


class RuntimeFactory:
    @staticmethod
    def build(config: AppConfig, *, broker_adapter: Any | None = None) -> Runtime:
        from runtime.broker_factory import build_broker_adapter

        bus_cfg = config.components.message_bus
        # ponytail: InMemoryMessageLog until file-backed log lands
        message_log = InMemoryMessageLog() if bus_cfg.persistent_log else None
        bus = MessageBus(max_queue_size=bus_cfg.max_queue_size, message_log=message_log)

        adapter = broker_adapter
        if adapter is None and config.environment in (
            Environment.LIVE,
            Environment.PAPER,
        ):
            adapter = build_broker_adapter(config)

        clock = resolve_clock(config.environment)
        fill_source = resolve_fill_source(config.environment, broker_adapter=adapter)

        cache = TradingCache()
        order_manager = OrderManager(cache)
        position_manager = PositionManager(cache)
        risk = _risk_from_config(config.components.risk)
        idem = _EngineIdempotency(IdempotencyGuard())

        engine = ExecutionEngine(
            fill_source=fill_source,
            risk_manager=risk,
            idempotency_guard=idem,
            order_manager=order_manager,
            position_manager=position_manager,
            trading_cache=cache,
            message_bus=bus,
            clock=clock,
            audit_sink=AuditSink(),
        )

        lifecycle = LifecycleManager()

        return Runtime(
            bus=bus,
            cache=cache,
            execution_engine=engine,
            risk=risk,
            lifecycle=lifecycle,
            environment=config.environment,
            fill_source=fill_source,
            clock=clock,
            environment_frozen=False,
            broker_adapter=adapter,
        )
