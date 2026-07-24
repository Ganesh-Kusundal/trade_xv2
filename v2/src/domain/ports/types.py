"""Supporting types referenced by port protocols."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from domain.enums import SignalDirection
from domain.events import Message
from domain.value_objects import (
    InstrumentId,
    Money,
    OrderId,
    Price,
    StrategyId,
)


# ---------------------------------------------------------------------------
# Strategy lifecycle events
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True, kw_only=True)
class StartEvent(Message):
    strategy_id: StrategyId


@dataclass(frozen=True, slots=True, kw_only=True)
class StopEvent(Message):
    strategy_id: StrategyId


# ---------------------------------------------------------------------------
# FillSource results
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True, kw_only=True)
class OrderResult:
    order_id: OrderId
    success: bool
    message: str = ""


@dataclass(frozen=True, slots=True, kw_only=True)
class CancelResult:
    success: bool
    message: str = ""


# ---------------------------------------------------------------------------
# Risk / Portfolio context
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class RiskContext:
    account_balance: Money
    open_positions: int = 0
    daily_pnl: Money = field(default_factory=lambda: Money(amount=Decimal("0"), currency="INR"))
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class PortfolioContext:
    account_balance: Money
    risk_budget: Money = field(default_factory=lambda: Money(amount=Decimal("0"), currency="INR"))
    metadata: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Broker snapshot
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class BrokerSnapshot:
    orders: list[Any] = field(default_factory=list)
    positions: list[Any] = field(default_factory=list)
    account: Any = None


# ---------------------------------------------------------------------------
# Signal
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class Signal:
    instrument_id: InstrumentId
    direction: SignalDirection
    strength: Price
    scanner_id: str = ""


# ---------------------------------------------------------------------------
# EventBus subscription handle
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class Subscription:
    token: int


# ---------------------------------------------------------------------------
# Idempotency result
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class IdempotencyResult:
    is_duplicate: bool
    previous_result: Any = None
