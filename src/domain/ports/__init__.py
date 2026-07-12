"""Application ports."""

from domain.ports.bootstrap import BootstrapResult, BootstrapStatus
from domain.ports.broker_gateway import OrderTransportPort
from domain.ports.broker_id import BrokerId
from domain.ports.correlation import CorrelationProviderPort
from domain.ports.event_log import (
    DeadLetterQueuePort,
    EventLogPort,
    ProcessedTradeRepositoryPort,
)
from domain.exceptions import ExchangeNotConfigured
from domain.ports.event_publisher import EventBusPort, EventPublisher
from domain.ports.exchange_adapter import ExchangeAdapter
from domain.ports.exchange_calendar import TradingCalendar
from domain.ports.execution_ledger import ExecutionLedgerPort
from domain.ports.lifecycle import LifecycleManagerPort, ManagedServicePort
from domain.ports.margin_provider import MarginProviderPort
from domain.ports.market_data import MarketDataPort
from domain.ports.metrics import MetricsRegistryPort
from domain.ports.observability import AlertingEnginePort, EventMetricsPort, TracerPort
from domain.ports.oms_backtest_adapter import OmsBacktestAdapterPort
from domain.ports.order_service import OrderServicePort
from domain.ports.order_store import OrderStorePort
from domain.ports.protocols import DataProvider, ExecutionProvider, OrderResult, SubscriptionHandle
from domain.ports.risk_manager import RiskManagerPort
from domain.ports.strategy_evaluator import StrategyEvaluator
from domain.ports.time_service import ClockPort, TimeServicePort

__all__ = [
    "AlertingEnginePort",
    "BootstrapResult",
    "BootstrapStatus",
    "ClockPort",
    "CorrelationProviderPort",
    "DataProvider",
    "DeadLetterQueuePort",
    "EventBusPort",
    "EventLogPort",
    "ExchangeNotConfigured",
    "EventMetricsPort",
    "EventPublisher",
    "ExchangeAdapter",
    "ExecutionLedgerPort",
    "ExecutionProvider",
    "LifecycleManagerPort",
    "ManagedServicePort",
    "MarginProviderPort",
    "MarketDataPort",
    "MetricsRegistryPort",
    "OmsBacktestAdapterPort",
    "OrderResult",
    "OrderServicePort",
    "OrderStorePort",
    "OrderTransportPort",
    "ProcessedTradeRepositoryPort",
    "RiskManagerPort",
    "StrategyEvaluator",
    "SubscriptionHandle",
    "TimeServicePort",
    "TracerPort",
]
