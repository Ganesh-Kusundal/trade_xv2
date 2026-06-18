"""Central position management system.

Single owner for position state. All position updates go through this manager.
Protected by one ``threading.RLock`` and uses immutable ``Position`` values.
"""

from __future__ import annotations

import logging
import threading
from decimal import Decimal
from typing import Any

from brokers.common.core.domain import Position, Trade
from brokers.common.core.state_machine import IllegalTransitionError, StateMachine
from brokers.common.core.types import POSITION_STATE_TRANSITIONS, PositionState
from brokers.common.event_bus import DomainEvent, EventBus, EventType

logger = logging.getLogger(__name__)


class PositionManager:
    """Thread-safe position book updated via trades and LTP ticks.

    The manager is intentionally a *downstream* consumer of the OMS:
    it subscribes to ``TRADE_APPLIED`` (published by :class:`OrderManager`
    after a trade passes idempotency) rather than to raw ``TRADE`` events.
    This guarantees that duplicate websocket fills cannot double-count
    positions: the OMS rejects them, and the position manager never
    sees them.
    """

    def __init__(
        self,
        event_bus: EventBus | None = None,
        processed_trade_repository: Any | None = None,
        metrics: Any | None = None,
        enforce_state_transitions: bool = False,  # P2-Phase 2: Audit-only by default
    ) -> None:
        self._lock = threading.RLock()
        self._positions: dict[str, Position] = {}
        self._event_bus = event_bus
        self._handler_depth: int = 0
        # Kept for backward compatibility; no longer used to gate writes.
        self._processed_trades = processed_trade_repository
        self._metrics = metrics
        self._trades_applied = 0
        
        # P2-Phase 2: State machine enforcement (audit-only mode first)
        self._enforce_state_transitions = enforce_state_transitions
        self._position_states: dict[str, StateMachine[PositionState]] = {}  # symbol_key -> StateMachine

    # ── Public API ──────────────────────────────────────────────────────────

    def apply_trade(self, trade: Trade) -> Position:
        """Apply a trade to the position book and return the new position.

        Idempotency is the OMS's responsibility: this method should only
        be called with trades that the OMS has already accepted.
        
        P2-Phase 2: Validates position state transitions using state machine.
        P1-Phase 1: Publishes POSITION_OPENED and POSITION_CLOSED lifecycle
        events in addition to existing POSITION_UPDATED.
        """
        symbol_key = self._key(trade.symbol, trade.exchange)
        with self._lock:
            current = self._positions.get(
                symbol_key, Position(symbol=trade.symbol, exchange=trade.exchange)
            )
            
            # P2-Phase 2: Determine current position state
            position_state = self._position_states.get(symbol_key)
            if position_state is None:
                # New position: starts at FLAT
                position_state = StateMachine(
                    transitions=POSITION_STATE_TRANSITIONS,
                    initial=PositionState.FLAT,
                )
                self._position_states[symbol_key] = position_state
            
            old_state = position_state.state
            was_flat = current.quantity == 0
            delta = trade.quantity if trade.side.value == "BUY" else -trade.quantity
            new_quantity = current.quantity + delta
            will_be_flat = new_quantity == 0
            
            # P2-Phase 2: Determine target state
            if was_flat and not will_be_flat:
                new_state = PositionState.OPEN
            elif not was_flat and will_be_flat:
                new_state = PositionState.CLOSED
            elif not was_flat and not will_be_flat:
                if abs(new_quantity) < abs(current.quantity):
                    new_state = PositionState.REDUCING
                elif (current.quantity > 0 and new_quantity < 0) or \
                     (current.quantity < 0 and new_quantity > 0):
                    new_state = PositionState.REVERSED
                else:
                    new_state = PositionState.OPEN  # Adding to position
            else:
                new_state = old_state  # No change
            
            # P2-Phase 2: Validate state transition
            if old_state != new_state:
                if not position_state.can_transition_to(new_state):
                    if self._enforce_state_transitions:
                        raise IllegalTransitionError(old_state, new_state)
                    else:
                        # Audit-only mode: log violation but accept
                        logger.warning(
                            "PositionManager: illegal position state transition "
                            "%s → %s for %s (audit mode: accepting)",
                            old_state.value,
                            new_state.value,
                            symbol_key,
                        )
                else:
                    # Valid transition: update state machine
                    position_state.transition_to(new_state)
            
            updated = current.with_fill(delta, trade.price)
            self._positions[symbol_key] = updated
            self._trades_applied += 1
            if self._metrics is not None:
                self._metrics.inc(EventType.TRADE_APPLIED.value, "position_updated")  # P1-3: Migrated to EventType enum
            
            # P1-Phase 1: Publish position lifecycle events
            if was_flat and not will_be_flat:
                # Flat → Open: POSITION_OPENED
                self._publish(
                    EventType.POSITION_OPENED.value,
                    payload={
                        "symbol": updated.symbol,
                        "quantity": updated.quantity,
                        "avg_price": float(updated.avg_price),
                    },
                )
            elif not was_flat and will_be_flat:
                # Open → Flat: POSITION_CLOSED
                self._publish(
                    EventType.POSITION_CLOSED.value,
                    payload={
                        "symbol": updated.symbol,
                        "realized_pnl": float(updated.realized_pnl) if hasattr(updated, 'realized_pnl') else 0.0,
                    },
                )
            
            # Always publish POSITION_UPDATED
            self._publish(EventType.POSITION_UPDATED.value, updated)  # P1-3: Migrated to EventType enum
            return updated

    def update_ltp(self, symbol: str, exchange: str, ltp: Decimal | float) -> Position | None:
        """Update last traded price for a position."""
        key = self._key(symbol, exchange)
        with self._lock:
            current = self._positions.get(key)
            if current is None:
                return None
            updated = current.with_ltp(Decimal(str(ltp)))
            self._positions[key] = updated
            return updated

    def get_position(self, symbol: str, exchange: str) -> Position | None:
        key = self._key(symbol, exchange)
        with self._lock:
            return self._positions.get(key)

    def get_positions(self) -> list[Position]:
        with self._lock:
            return list(self._positions.values())

    def get_positions_as_dicts(self) -> list[dict]:
        """Return all positions as list of dicts for reconciliation compatibility."""
        with self._lock:
            return [
                {
                    "symbol": p.symbol,
                    "exchange": p.exchange,
                    "quantity": p.quantity,
                    "avg_price": str(p.avg_price),
                    "ltp": str(p.ltp),
                    "unrealized_pnl": str(p.unrealized_pnl) if hasattr(p, "unrealized_pnl") else "0",
                }
                for p in self._positions.values()
            ]

    def upsert_position(self, data: dict) -> Position:
        """Create or update a position from broker state (used by reconciliation).

        Accepts either a dict with ``symbol``/``exchange``/``quantity`` keys,
        or a dict with ``exchange_segment``/``trading_symbol``/``net_quantity``
        keys (Upstox format).
        """
        symbol = data.get("symbol") or data.get("trading_symbol", "")
        exchange = data.get("exchange") or data.get("exchange_segment", "NSE")
        quantity = int(data.get("quantity") or data.get("net_quantity") or 0)
        avg_price = Decimal(str(data.get("avg_price") or data.get("average_price") or 0))
        ltp = Decimal(str(data.get("ltp") or data.get("last_price") or 0))
        if not symbol:
            raise ValueError("Position data must contain 'symbol' or 'trading_symbol'")
        key = self._key(symbol, exchange)
        with self._lock:
            current = self._positions.get(key)
            if current is None:
                pos = Position(symbol=symbol, exchange=exchange)
                pos = pos.with_fill(quantity, avg_price) if quantity else pos
                if ltp:
                    pos = pos.with_ltp(ltp)
                self._positions[key] = pos
                self._publish(EventType.POSITION_UPDATED.value, pos)  # P1-3: Migrated to EventType enum
                return pos
            # Update existing position
            delta = quantity - current.quantity
            updated = current.with_fill(delta, avg_price) if delta != 0 else current
            if ltp:
                updated = updated.with_ltp(ltp)
            self._positions[key] = updated
            self._publish(EventType.POSITION_UPDATED.value, updated)  # P1-3: Migrated to EventType enum
            return updated

    def reset(self) -> None:
        """Clear all positions. Useful in tests."""
        with self._lock:
            self._positions.clear()

    # ── Event handler ───────────────────────────────────────────────────────

    def on_trade(self, event: DomainEvent) -> None:
        """Handle broker trade events from the event bus.

        Re-entrancy: a position update that the manager itself publishes
        (via :meth:`apply_trade` or :meth:`upsert_position`) must not
        re-enter this handler.

        Thread-safe: the depth guard is inside ``_lock`` (see
        :class:`OrderManager.on_order_update`).
        """
        with self._lock:
            if self._handler_depth > 0:
                return
            self._handler_depth += 1
        try:
            trade = event.payload.get("trade")
            if isinstance(trade, Trade):
                self.apply_trade(trade)
        finally:
            with self._lock:
                self._handler_depth -= 1

    def on_trade_applied(self, event: DomainEvent) -> None:
        """Apply a trade that has been verified by the OMS.

        Use this handler in production wiring; subscribing to raw
        ``TRADE`` events would bypass OMS idempotency and risk
        double-counting positions.

        Thread-safe: the depth guard is inside ``_lock``.
        """
        with self._lock:
            if self._handler_depth > 0:
                return
            self._handler_depth += 1
        try:
            trade = event.payload.get("trade")
            if isinstance(trade, Trade):
                self.apply_trade(trade)
        finally:
            with self._lock:
                self._handler_depth -= 1

    # ── Helpers ─────────────────────────────────────────────────────────────

    @staticmethod
    def _key(symbol: str, exchange: str) -> str:
        return f"{symbol.upper()}:{exchange.upper()}"

    def _publish(self, event_type: str, position: Position) -> None:
        if self._event_bus is None:
            return
        self._event_bus.publish(
            DomainEvent.now(
                event_type,
                {"position": position},
                symbol=position.symbol,
                source="PositionManager",
            )
        )
