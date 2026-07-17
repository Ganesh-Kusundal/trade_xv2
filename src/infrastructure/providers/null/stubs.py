from typing import Any
import logging

logger = logging.getLogger(__name__)

class NullEventBus:
    def __init__(self) -> None:
        self._warned = False
        self._replay_mode = False
        self._logging_enabled = False

    def _warn(self, method: str) -> None:
        if not self._warned:
            logger.warning(f"NullEventBus.{method} called. No real EventBus is configured.")
            self._warned = True

    def publish(self, event: Any) -> None:
        self._warn("publish")

    def subscribe(self, event_type: str, handler: Any) -> str:
        self._warn("subscribe")
        return "null-token"

    def unsubscribe(self, token: str) -> bool:
        self._warn("unsubscribe")
        return False

    @property
    def replay_mode(self) -> bool:
        return self._replay_mode

    def set_replay_mode(self, enabled: bool) -> None:
        self._replay_mode = enabled

    @property
    def logging_enabled(self) -> bool:
        return self._logging_enabled

    def set_logging_enabled(self, enabled: bool) -> None:
        self._logging_enabled = enabled

class NullOrderManager:
    def __init__(self) -> None:
        self._warned = False

    def _warn(self, method: str) -> None:
        if not self._warned:
            logger.warning(f"NullOrderManager.{method} called. No real OrderManager is configured.")
            self._warned = True

    def place(self, intent: Any) -> Any:
        self._warn("place")
        from domain.ports.protocols import OrderResult
        return OrderResult(success=False, error="NullOrderManager active", order_id="")

    def cancel(self, order_id: str) -> Any:
        self._warn("cancel")
        from domain.ports.protocols import OrderResult
        return OrderResult(success=False, error="NullOrderManager active", order_id="")

    def modify(self, request: Any) -> Any:
        self._warn("modify")
        from domain.ports.protocols import OrderResult
        return OrderResult(success=False, error="NullOrderManager active", order_id="")

class NullRiskManager:
    def __init__(self) -> None:
        self._warned = False

    def _warn(self, method: str) -> None:
        if not self._warned:
            logger.warning(f"NullRiskManager.{method} called. No real RiskManager is configured.")
            self._warned = True

    def evaluate_order(self, intent: Any) -> Any:
        self._warn("evaluate_order")
        from domain.risk.models import RiskResult
        return RiskResult(allowed=False, reason="NullRiskManager active")

class NullBrokerService:
    def __init__(self) -> None:
        self._warned = False
        self.active_broker = None
        self.active_broker_name = "null"

    def _warn(self, method: str) -> None:
        if not self._warned:
            logger.warning(f"NullBrokerService.{method} called. No real BrokerService is configured.")
            self._warned = True

class NullDataLakeGateway:
    pass

class NullViewManager:
    pass

class NullDataCatalog:
    pass

class NullMarketDataComposer:
    def __init__(self) -> None:
        self._warned = False

    def _warn(self, method: str) -> None:
        if not self._warned:
            logger.warning(f"NullMarketDataComposer.{method} called.")
            self._warned = True

    def get_quote(self, symbol: str) -> Any:
        self._warn("get_quote")
        return None

class NullExecutionComposer:
    pass

class NullPositionManager:
    pass
