"""Internal OMS components — not part of the public API.

Prefer public re-exports from :mod:`application.oms` in application code.
"""

from application.oms._internal.loss_circuit_breaker import (
    LossCircuitBreaker,
    LossCircuitState,
)
from application.oms._internal.order_audit_logger import OrderAuditLogger
from application.oms._internal.order_position_updater import OrderPositionUpdater
from application.oms._internal.order_state_validator import OrderStateValidator
from application.oms._internal.risk_manager import RiskConfig, RiskManager
from application.oms._internal.risk_types import (
    InstrumentProvider,
    RiskResult,
    risk_result_from_domain,
)
from application.oms._internal.margin_checker import MarginChecker
from application.oms._internal.kill_switch import KillSwitch
from application.oms._internal.daily_pnl_tracker import DailyPnlTracker

__all__ = [
    # Circuit breaker
    "LossCircuitBreaker",
    "LossCircuitState",
    # Audit & logging
    "OrderAuditLogger",
    # Position updates
    "OrderPositionUpdater",
    "OrderStateValidator",
    # Risk & validation
    "RiskConfig",
    "RiskManager",
    "RiskResult",
    "InstrumentProvider",
    "risk_result_from_domain",
    "MarginChecker",
    "KillSwitch",
    "DailyPnlTracker",
]
