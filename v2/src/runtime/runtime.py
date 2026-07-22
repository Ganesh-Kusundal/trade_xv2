"""Runtime — frozen composition-root handle."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from application.execution.protocols import FillSource
from application.oms.trading_cache import TradingCache
from application.risk.risk_manager import RiskManager
from config.schema import Environment
from infrastructure.component.lifecycle import LifecycleManager
from infrastructure.message_bus.bus import MessageBus


@dataclass(frozen=True)
class Runtime:
    bus: MessageBus
    cache: TradingCache
    execution_engine: Any
    risk: RiskManager | None
    lifecycle: LifecycleManager
    environment: Environment
    fill_source: FillSource
    clock: Any
    environment_frozen: bool = False
    broker_adapter: Any | None = None
