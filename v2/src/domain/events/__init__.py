"""Domain events — immutable Message hierarchy."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from domain.enums import (
    BrokerId,
    ComponentState,
    DriftSeverity,
    Environment,
    OrderSide,
    OrderType,
    RiskLevel,
    SignalDirection,
    TimeInForce,
)
from domain.value_objects import (
    AccountId,
    ComponentId,
    InstrumentId,
    Money,
    OrderId,
    Price,
    Quantity,
    StrategyId,
    TimeFrame,
)


# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True, kw_only=True)
class Message:
    timestamp: datetime
    correlation_id: UUID | None = None
    source: ComponentId | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class DomainEvent(Message):
    """Base domain event."""


# ---------------------------------------------------------------------------
# Category markers (empty bases)
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True, kw_only=True)
class MarketDataMessage(DomainEvent):
    """Marker for market-data messages."""


@dataclass(frozen=True, slots=True, kw_only=True)
class OrderMessage(DomainEvent):
    """Marker for order lifecycle messages."""


@dataclass(frozen=True, slots=True, kw_only=True)
class PortfolioMessage(DomainEvent):
    """Marker for portfolio/account messages."""


@dataclass(frozen=True, slots=True, kw_only=True)
class RiskMessage(DomainEvent):
    """Marker for risk messages."""


@dataclass(frozen=True, slots=True, kw_only=True)
class SystemMessage(DomainEvent):
    """Marker for system messages."""


@dataclass(frozen=True, slots=True, kw_only=True)
class RankMessage(DomainEvent):
    """Marker for analytics/ranking messages."""


# ---------------------------------------------------------------------------
# Market Data
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True, kw_only=True)
class Quote(MarketDataMessage):
    instrument_id: InstrumentId
    bid_price: Price
    ask_price: Price
    bid_size: Quantity
    ask_size: Quantity


@dataclass(frozen=True, slots=True, kw_only=True)
class Trade(MarketDataMessage):
    instrument_id: InstrumentId
    price: Price
    size: Quantity


@dataclass(frozen=True, slots=True, kw_only=True)
class Bar(MarketDataMessage):
    instrument_id: InstrumentId
    open: Price
    high: Price
    low: Price
    close: Price
    volume: Quantity
    timeframe: TimeFrame


@dataclass(frozen=True, slots=True, kw_only=True)
class OrderBook(MarketDataMessage):
    instrument_id: InstrumentId
    bids: tuple[tuple[Price, Quantity], ...]
    asks: tuple[tuple[Price, Quantity], ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class Tick(MarketDataMessage):
    instrument_id: InstrumentId
    price: Price
    size: Quantity
    side: OrderSide


# ---------------------------------------------------------------------------
# Order
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True, kw_only=True)
class OrderCommand(OrderMessage):
    instrument_id: InstrumentId
    side: OrderSide
    order_type: OrderType
    quantity: Quantity
    price: Price | None
    time_in_force: TimeInForce


@dataclass(frozen=True, slots=True, kw_only=True)
class OrderPlaced(OrderMessage):
    order_id: OrderId
    instrument_id: InstrumentId
    side: OrderSide
    quantity: Quantity


@dataclass(frozen=True, slots=True, kw_only=True)
class OrderFilled(OrderMessage):
    order_id: OrderId
    instrument_id: InstrumentId
    side: OrderSide
    filled_qty: Quantity
    avg_price: Price


@dataclass(frozen=True, slots=True, kw_only=True)
class OrderCancelled(OrderMessage):
    order_id: OrderId
    reason: str


@dataclass(frozen=True, slots=True, kw_only=True)
class OrderRejected(OrderMessage):
    order_id: OrderId
    reason: str
    venue_code: str


@dataclass(frozen=True, slots=True, kw_only=True)
class OrderModified(OrderMessage):
    order_id: OrderId
    new_quantity: Quantity
    new_price: Price


# ---------------------------------------------------------------------------
# Portfolio
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True, kw_only=True)
class PositionUpdated(PortfolioMessage):
    account_id: AccountId
    instrument_id: InstrumentId
    quantity: Quantity
    avg_price: Price
    realized_pnl: Price
    unrealized_pnl: Price


@dataclass(frozen=True, slots=True, kw_only=True)
class PositionChanged(PortfolioMessage):
    instrument_id: InstrumentId
    quantity: Quantity
    avg_price: Price
    realized_pnl: Money
    unrealized_pnl: Money


@dataclass(frozen=True, slots=True, kw_only=True)
class AccountUpdated(PortfolioMessage):
    account_id: AccountId
    balance: Price
    margin: Price
    equity: Price


@dataclass(frozen=True, slots=True, kw_only=True)
class PnLUpdated(PortfolioMessage):
    account_id: AccountId
    realized: Price
    unrealized: Price
    total: Price


# ---------------------------------------------------------------------------
# Risk
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True, kw_only=True)
class RiskCheckResult(RiskMessage):
    """Bus-published risk-check outcome (spec message catalog).

    Distinct from application.risk.context.RiskCheckResult, the synchronous DTO
    passed between RiskRulesEngine/RiskManager/ExecutionEngine — that one is never
    published. Nothing currently publishes *this* one either; kept for message-
    hierarchy completeness (tests/unit/domain/test_messages.py) until something
    needs to broadcast risk-check outcomes on the bus.
    """

    approved: bool
    reason: str
    max_quantity: Quantity
    max_notional: Price


@dataclass(frozen=True, slots=True, kw_only=True)
class RiskRejected(RiskMessage):
    order_id: OrderId
    reason: str
    correlation_id: UUID | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class RiskAlert(RiskMessage):
    level: RiskLevel
    reason: str
    instrument_id: InstrumentId | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class RiskBreached(RiskMessage):
    level: RiskLevel
    reason: str
    instrument_id: InstrumentId | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class AutoFlattenOrder(RiskMessage):
    instrument_id: InstrumentId
    reason: str


# ---------------------------------------------------------------------------
# System
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True, kw_only=True)
class Startup(SystemMessage):
    environment: Environment
    broker_id: BrokerId
    config_hash: str


@dataclass(frozen=True, slots=True, kw_only=True)
class Shutdown(SystemMessage):
    reason: str


@dataclass(frozen=True, slots=True, kw_only=True)
class ComponentHealth(SystemMessage):
    component_id: ComponentId
    state: ComponentState
    metrics: dict[str, float]


@dataclass(frozen=True, slots=True, kw_only=True)
class ReconciliationDrift(SystemMessage):
    drift_items: list[str]
    severity: DriftSeverity


@dataclass(frozen=True, slots=True, kw_only=True)
class ReconciliationCompleted(SystemMessage):
    items_healed: int
    duration_ms: int


@dataclass(frozen=True, slots=True, kw_only=True)
class BrokerDisconnected(SystemMessage):
    broker_id: BrokerId
    reason: str


@dataclass(frozen=True, slots=True, kw_only=True)
class BrokerReconnected(SystemMessage):
    broker_id: BrokerId


@dataclass(frozen=True, slots=True, kw_only=True)
class ReplayStarted(SystemMessage):
    session_id: str
    start_ts: datetime
    end_ts: datetime


@dataclass(frozen=True, slots=True, kw_only=True)
class ReplayCompleted(SystemMessage):
    session_id: str
    events_replayed: int
    duration_ms: int


@dataclass(frozen=True, slots=True, kw_only=True)
class FeatureComputed(SystemMessage):
    instrument_id: InstrumentId
    feature_name: str
    value: Price
    feature_timestamp: datetime


# ---------------------------------------------------------------------------
# Analytics
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True, kw_only=True)
class SignalGenerated(RankMessage):
    instrument_id: InstrumentId
    direction: SignalDirection
    strength: Price
    scanner_id: str


@dataclass(frozen=True, slots=True, kw_only=True)
class ScanCompleted(RankMessage):
    scanner_id: str
    signal_count: int
    universe_size: int


@dataclass(frozen=True, slots=True, kw_only=True)
class BacktestCompleted(RankMessage):
    strategy_id: StrategyId
    metrics: dict[str, float]
    trade_count: int


@dataclass(frozen=True, slots=True, kw_only=True)
class RankingUpdated(RankMessage):
    universe: str
    rankings: list[str]
