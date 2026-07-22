# 08 — Risk Management

## 1. Overview

Risk management in TradeXV2 is a multi-layered system that operates at
different stages of the order lifecycle:

```
┌─────────────────────────────────────────────────────────────┐
│                    RiskManager                              │
│                                                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐  │
│  │  Pre-Trade   │  │  Post-Trade  │  │  Kill Switch     │  │
│  │  Checks      │  │  Monitoring  │  │  (Emergency)     │  │
│  └──────┬───────┘  └──────┬───────┘  └────────┬─────────┘  │
│         │                 │                    │            │
│         ▼                 ▼                    ▼            │
│  ┌─────────────────────────────────────────────────────┐   │
│  │              Risk Rules Engine                       │   │
│  │   (Position limits, order size, daily loss, etc.)   │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

## 2. Risk Layers

### 2.1 Pre-Trade Checks (Before Order Submission)

| Check | Description | Action on Breach |
|---|---|---|
| **Position Limit** | Max quantity per symbol | Reject order |
| **Order Size Limit** | Max quantity per order | Reject order |
| **Daily Loss Limit** | Max loss per day | Reject order + alert |
| **Margin Check** | Sufficient funds | Reject order |
| **Concentration Limit** | Max % of capital in one symbol | Reject order |
| **Sector Limit** | Max exposure per sector | Reject order |
| **Order Rate Limit** | Max orders per minute | Throttle / reject |
| **Market Hours** | Trading session check | Reject order |

### 2.2 Post-Trade Monitoring (After Fill)

| Check | Description | Action on Breach |
|---|---|---|
| **Realized P&L** | Track daily P&L | Alert / kill switch |
| **Unrealized P&L** | Track MTM | Alert / kill switch |
| **Drawdown** | Peak-to-trough decline | Kill switch |
| **Position Concentration** | Post-fill concentration | Alert |
| **Greeks Exposure** | Option portfolio risk | Alert / hedge |

### 2.3 Kill Switch (Emergency Stop)

| Trigger | Description | Action |
|---|---|---|
| **Daily Loss Limit** | Loss exceeds threshold | Cancel all orders, flatten positions |
| **Max Drawdown** | Drawdown exceeds threshold | Cancel all orders, flatten positions |
| **Manual Trigger** | Operator presses kill switch | Cancel all orders, flatten positions |
| **Broker Disconnect** | Loss of broker connection | Pause new orders, alert |
| **System Error** | Critical component failure | Pause all trading, alert |

## 3. Core Implementation

```python
# application/risk/risk_manager.py

from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from domain.commands.order_commands import PlaceOrderCommand
from domain.entities.trade import Trade
from domain.events.order_events import OrderRejected, RiskBreached
from domain.events.risk_events import KillSwitchActivated
from domain.ports.event_bus import EventBusPort
from shared.messaging.component import Component


logger = logging.getLogger(__name__)


@dataclass
class RiskCheckResult:
    ok: bool
    reason: str = ""
    rule_name: str = ""


@dataclass
class RiskConfig:
    max_position_qty: Decimal = Decimal("1000")
    max_order_qty: Decimal = Decimal("500")
    max_daily_loss: Decimal = Decimal("50000")
    max_capital_per_symbol: Decimal = Decimal("200000")
    max_orders_per_minute: int = 60
    max_drawdown_pct: Decimal = Decimal("5")  # 5%


class RiskManager(Component):
    """
    Multi-layer risk management.

    Performs pre-trade checks, post-trade monitoring, and kill switch logic.
    """

    def __init__(
        self,
        bus: EventBusPort,
        initial_capital: float = 1_000_000.0,
        config: Optional[RiskConfig] = None,
    ) -> None:
        super().__init__(component_id="RiskManager", bus=bus)
        self._initial_capital = initial_capital
        self._config = config or RiskConfig()
        self._daily_pnl = Decimal("0")
        self._peak_capital = initial_capital
        self._positions: dict[tuple[str, str], Decimal] = {}  # (symbol, exchange) -> qty
        self._order_count_minute = 0
        self._kill_switch_active = False

    # ── Pre-Trade Checks ──────────────────────────────────────

    def check_order(self, command: PlaceOrderCommand) -> RiskCheckResult:
        """Run all pre-trade risk checks."""
        if self._kill_switch_active:
            return RiskCheckResult(ok=False, reason="Kill switch active", rule_name="kill_switch")

        # Position limit
        qty = Decimal(command.quantity)
        current_qty = self._positions.get((command.symbol, command.exchange), Decimal("0"))
        new_qty = current_qty + qty if command.side.value == "BUY" else current_qty - qty
        if abs(new_qty) > self._config.max_position_qty:
            return RiskCheckResult(
                ok=False,
                reason=f"Position limit exceeded: {abs(new_qty)} > {self._config.max_position_qty}",
                rule_name="position_limit",
            )

        # Order size limit
        if qty > self._config.max_order_qty:
            return RiskCheckResult(
                ok=False,
                reason=f"Order size limit exceeded: {qty} > {self._config.max_order_qty}",
                rule_name="order_size_limit",
            )

        # Daily loss limit
        if self._daily_pnl < -self._config.max_daily_loss:
            return RiskCheckResult(
                ok=False,
                reason=f"Daily loss limit exceeded: {self._daily_pnl}",
                rule_name="daily_loss_limit",
            )

        # Order rate limit
        if self._order_count_minute >= self._config.max_orders_per_minute:
            return RiskCheckResult(
                ok=False,
                reason=f"Order rate limit exceeded: {self._order_count_minute}/min",
                rule_name="order_rate_limit",
            )

        return RiskCheckResult(ok=True)

    # ── Post-Trade ────────────────────────────────────────────

    def on_fill(self, trade: Trade) -> None:
        """Update risk state after a fill."""
        # Update position
        key = (trade.symbol, trade.exchange)
        current_qty = self._positions.get(key, Decimal("0"))
        if trade.side == "BUY":
            self._positions[key] = current_qty + trade.quantity.value
        else:
            self._positions[key] = current_qty - trade.quantity.value

        # Update daily P&L
        self._daily_pnl -= trade.commission.amount

        # Check drawdown
        current_capital = self._initial_capital + float(self._daily_pnl)
        if current_capital > self._peak_capital:
            self._peak_capital = current_capital
        drawdown_pct = ((self._peak_capital - current_capital) / self._peak_capital) * 100
        if drawdown_pct > float(self._config.max_drawdown_pct):
            self._activate_kill_switch(
                reason=f"Max drawdown exceeded: {drawdown_pct:.2f}%",
                triggered_by="drawdown_check",
            )

    # ── Kill Switch ───────────────────────────────────────────

    def activate_kill_switch(self, reason: str) -> None:
        """Manually activate kill switch."""
        self._activate_kill_switch(reason, triggered_by="manual")

    def _activate_kill_switch(self, reason: str, triggered_by: str) -> None:
        """Activate kill switch and publish event."""
        self._kill_switch_active = True
        event = KillSwitchActivated(
            reason=reason,
            triggered_by=triggered_by,
            source="RiskManager",
        )
        self._publish(event)
        logger.critical("KILL SWITCH ACTIVATED: %s", reason)

    def reset_kill_switch(self) -> None:
        """Reset kill switch (requires manual intervention)."""
        self._kill_switch_active = False
        logger.info("Kill switch reset")

    # ── Daily Reset ───────────────────────────────────────────

    def reset_daily(self) -> None:
        """Reset daily counters (call at start of trading day)."""
        self._daily_pnl = Decimal("0")
        self._order_count_minute = 0
        self._positions.clear()
        logger.info("Daily risk counters reset")

    # ── Queries ───────────────────────────────────────────────

    @property
    def daily_pnl(self) -> Decimal:
        return self._daily_pnl

    @property
    def is_kill_switch_active(self) -> bool:
        return self._kill_switch_active

    def get_position(self, symbol: str, exchange: str) -> Decimal:
        return self._positions.get((symbol, exchange), Decimal("0"))

    def get_all_positions(self) -> dict[tuple[str, str], Decimal]:
        return dict(self._positions)
```

## 4. Risk Rules Engine

```python
# application/risk/rules.py

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Callable, Protocol

from domain.commands.order_commands import PlaceOrderCommand


class RiskRule(Protocol):
    """Protocol for pluggable risk rules."""

    def check(self, command: PlaceOrderCommand, context: RiskContext) -> RiskCheckResult:
        ...


@dataclass
class RiskContext:
    """Context passed to risk rules."""
    current_positions: dict[tuple[str, str], Decimal]
    daily_pnl: Decimal
    available_margin: Decimal
    order_count_minute: int


class PositionLimitRule:
    """Reject orders that exceed position limit."""

    def __init__(self, max_qty: Decimal) -> None:
        self._max_qty = max_qty

    def check(self, command: PlaceOrderCommand, context: RiskContext) -> RiskCheckResult:
        qty = Decimal(command.quantity)
        current = context.current_positions.get((command.symbol, command.exchange), Decimal("0"))
        new_qty = current + qty if command.side.value == "BUY" else current - qty
        if abs(new_qty) > self._max_qty:
            return RiskCheckResult(
                ok=False,
                reason=f"Position limit: {abs(new_qty)} > {self._max_qty}",
                rule_name="position_limit",
            )
        return RiskCheckResult(ok=True)


class OrderSizeRule:
    """Reject orders that exceed size limit."""

    def __init__(self, max_qty: Decimal) -> None:
        self._max_qty = max_qty

    def check(self, command: PlaceOrderCommand, context: RiskContext) -> RiskCheckResult:
        qty = Decimal(command.quantity)
        if qty > self._max_qty:
            return RiskCheckResult(
                ok=False,
                reason=f"Order size: {qty} > {self._max_qty}",
                rule_name="order_size",
            )
        return RiskCheckResult(ok=True)


class DailyLossRule:
    """Reject orders when daily loss exceeds limit."""

    def __init__(self, max_loss: Decimal) -> None:
        self._max_loss = max_loss

    def check(self, command: PlaceOrderCommand, context: RiskContext) -> RiskCheckResult:
        if context.daily_pnl < -self._max_loss:
            return RiskCheckResult(
                ok=False,
                reason=f"Daily loss: {context.daily_pnl} < -{self._max_loss}",
                rule_name="daily_loss",
            )
        return RiskCheckResult(ok=True)


class RiskRulesEngine:
    """Composable risk rules engine."""

    def __init__(self, rules: list[RiskRule]) -> None:
        self._rules = rules

    def check(self, command: PlaceOrderCommand, context: RiskContext) -> RiskCheckResult:
        """Run all rules. Returns first failure or OK."""
        for rule in self._rules:
            result = rule.check(command, context)
            if not result.ok:
                return result
        return RiskCheckResult(ok=True)
```

## 5. Integration with ExecutionEngine

```python
# In ExecutionEngine._on_place_order:

def _on_place_order(self, command: PlaceOrderCommand) -> None:
    # 1. Build risk context
    context = RiskContext(
        current_positions=self._risk_manager.get_all_positions(),
        daily_pnl=self._risk_manager.daily_pnl,
        available_margin=self._get_available_margin(),
        order_count_minute=self._risk_manager._order_count_minute,
    )

    # 2. Run risk checks
    risk_result = self._risk_manager.check_order(command)
    if not risk_result.ok:
        self._publish(OrderRejected(
            order_id=command.command_id,
            reason=risk_result.reason,
            source="RiskManager",
        ))
        return

    # 3. Proceed with order
    # ...
```

## 6. Risk Metrics & Monitoring

```python
# application/risk/risk_metrics.py

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass
class RiskMetrics:
    """Real-time risk metrics."""
    daily_pnl: Decimal
    realized_pnl: Decimal
    unrealized_pnl: Decimal
    total_exposure: Decimal
    position_count: int
    largest_position: Decimal
    drawdown_pct: Decimal
    orders_today: int
    kill_switch_active: bool

    def to_dict(self) -> dict:
        return {
            "daily_pnl": float(self.daily_pnl),
            "realized_pnl": float(self.realized_pnl),
            "unrealized_pnl": float(self.unrealized_pnl),
            "total_exposure": float(self.total_exposure),
            "position_count": self.position_count,
            "largest_position": float(self.largest_position),
            "drawdown_pct": float(self.drawdown_pct),
            "orders_today": self.orders_today,
            "kill_switch_active": self.kill_switch_active,
        }
```

## 7. Comparison with Current State

| Aspect | Current | Target |
|---|---|---|
| Risk checks | Inline in engine | Separate `RiskManager` component |
| Rules | Hardcoded | Pluggable `RiskRule` protocol |
| Kill switch | Not formalized | Explicit kill switch with events |
| Daily reset | Manual | Automated `reset_daily()` |
| Metrics | Ad hoc | Structured `RiskMetrics` |
| Post-trade monitoring | None | Drawdown, P&L, concentration checks |

## 8. Testing Strategy

```python
# tests/unit/test_risk_manager.py

def test_position_limit_rejects_order():
    bus = MessageBus()
    risk = RiskManager(bus, config=RiskConfig(max_position_qty=Decimal("100")))
    risk.initialize()
    risk.start()

    # Fill up position
    risk._positions[("RELIANCE", "NSE")] = Decimal("90")

    # Try to add more
    result = risk.check_order(PlaceOrderCommand(
        symbol="RELIANCE", exchange="NSE", side=OrderSide.BUY, quantity="20",
    ))
    assert not result.ok
    assert "Position limit" in result.reason

def test_kill_switch_blocks_all_orders():
    bus = MessageBus()
    risk = RiskManager(bus)
    risk.initialize()
    risk.start()

    risk.activate_kill_switch("Test")

    result = risk.check_order(PlaceOrderCommand(
        symbol="RELIANCE", exchange="NSE", side=OrderSide.BUY, quantity="10",
    ))
    assert not result.ok
    assert "Kill switch" in result.reason

def test_daily_loss_triggers_kill_switch():
    bus = MessageBus()
    risk = RiskManager(bus, config=RiskConfig(max_daily_loss=Decimal("1000")))
    risk.initialize()
    risk.start()

    events = []
    bus.subscribe(KillSwitchActivated, lambda e: events.append(e))

    # Simulate large loss
    risk._daily_pnl = Decimal("-1500")
    risk.on_fill(Trade(...))  # Triggers drawdown check

    assert risk.is_kill_switch_active
    assert len(events) == 1
```
