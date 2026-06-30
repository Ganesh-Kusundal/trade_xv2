"""Central position management system.

Single owner for position state. All position updates go through this manager.
Protected by one ``threading.RLock`` and uses immutable ``Position`` values.
"""

from __future__ import annotations

import threading
from collections import deque
from decimal import Decimal

from application.oms._internal.reentrancy_guard import _ReentrancyGuard
from domain.entities import Position, Trade
from domain.symbols import make_position_key
from domain.types import POSITION_STATE_TRANSITIONS, PositionState
from infrastructure.event_bus import DomainEvent, EventBus, EventType, ProcessedTradeRepository
from infrastructure.logging_config import get_logger
from infrastructure.observability.event_metrics import EventMetrics
from infrastructure.state_machine import IllegalTransitionError, StateMachine

logger = get_logger(__name__)


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
        processed_trade_repository: ProcessedTradeRepository | None = None,
        metrics: EventMetrics | None = None,
        enforce_state_transitions: bool = True,
    ) -> None:
        self._lock = threading.RLock()
        self._positions: dict[str, Position] = {}
        self._event_bus = event_bus
        self._handler_depth: int = 0
        # Kept for backward compatibility; no longer used to gate writes.
        self._processed_trades = processed_trade_repository
        self._metrics = metrics
        self._trades_applied = 0

        # P5 Stability Engineering: In-memory idempotency cache for trade_ids
        # to prevent duplicate processing under at-least-once delivery.
        # This is separate from the persistent repository (crash recovery).
        # Bounded LRU cache (deque + set) to prevent unbounded memory growth.
        # Thread-safe: all mutations are protected by _lock.
        self._processed_trade_id_set: set[str] = set()
        self._processed_trade_id_order: deque[str] = deque(maxlen=10_000)

        self._enforce_state_transitions = enforce_state_transitions
        self._position_states: dict[
            str, StateMachine[PositionState]
        ] = {}  # symbol_key -> StateMachine

    # ── Public API ──────────────────────────────────────────────────────────

    def apply_trade(self, trade: Trade) -> Position:
        """Apply a trade to the position book and return the new position.

        REF-020: Event publishing is collected under the lock but
        executed after release, preventing nested lock acquisitions
        when event handlers re-enter the manager.
        """
        symbol_key = self._key(trade.symbol, trade.exchange)
        events_to_publish: list[tuple[str, dict | Position]] = []

        with self._lock:
            current = self._positions.get(
                symbol_key, Position(symbol=trade.symbol, exchange=trade.exchange)
            )

            position_state = self._position_states.get(symbol_key)
            if position_state is None:
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

            if was_flat and not will_be_flat:
                new_state = PositionState.OPEN
            elif not was_flat and will_be_flat:
                new_state = PositionState.CLOSED
            elif not was_flat and not will_be_flat:
                if abs(new_quantity) < abs(current.quantity):
                    new_state = PositionState.REDUCING
                elif (current.quantity > 0 and new_quantity < 0) or (
                    current.quantity < 0 and new_quantity > 0
                ):
                    new_state = PositionState.REVERSED
                else:
                    new_state = PositionState.OPEN
            else:
                new_state = old_state

            if old_state != new_state:
                if not position_state.can_transition_to(new_state):
                    if self._enforce_state_transitions:
                        raise IllegalTransitionError(old_state, new_state)
                    else:
                        logger.warning(
                            "PositionManager: illegal position state transition "
                            "%s → %s for %s (audit mode: accepting)",
                            old_state.value,
                            new_state.value,
                            symbol_key,
                        )
                else:
                    position_state.transition_to(new_state)

            updated = current.with_fill(delta, trade.price)
            self._positions[symbol_key] = updated
            self._trades_applied += 1
            if self._metrics is not None:
                self._metrics.inc(EventType.TRADE_APPLIED.value, "position_updated")

            # Collect events under lock, publish after release
            if was_flat and not will_be_flat:
                events_to_publish.append(
                    (
                        EventType.POSITION_OPENED.value,
                        {
                            "symbol": updated.symbol,
                            "quantity": updated.quantity,
                            "avg_price": float(updated.avg_price),
                        },
                    )
                )
            elif not was_flat and will_be_flat:
                events_to_publish.append(
                    (
                        EventType.POSITION_CLOSED.value,
                        {
                            "symbol": updated.symbol,
                            "realized_pnl": float(updated.realized_pnl)
                            if hasattr(updated, "realized_pnl")
                            else 0.0,
                        },
                    )
                )
            events_to_publish.append((EventType.POSITION_UPDATED.value, updated))

        # Publish events OUTSIDE the lock to avoid holding it during dispatch
        for event_type, data in events_to_publish:
            self._publish(
                event_type,
                data if isinstance(data, Position) else None,
                payload=data if isinstance(data, dict) else None,
            )

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
                    "unrealized_pnl": str(p.unrealized_pnl)
                    if hasattr(p, "unrealized_pnl")
                    else "0",
                }
                for p in self._positions.values()
            ]

    def upsert_position(self, data: dict) -> Position:
        """Create or update a position from broker state (used by reconciliation).

        Accepts a dict with ``symbol``/``exchange``/``quantity`` keys.
        Also normalizes Upstox-specific keys for backward compatibility.
        """
        # Normalize Upstox-specific keys to domain format
        _KEY_MAP = {
            "trading_symbol": "symbol",
            "exchange_segment": "exchange",
            "net_quantity": "quantity",
            "buy_average_price": "avg_price",
            "average_price": "avg_price",
            "last_price": "ltp",
        }
        normalized = {_KEY_MAP.get(k, k): v for k, v in data.items()}

        symbol = normalized.get("symbol", "")
        exchange = normalized.get("exchange", "NSE")
        quantity = int(normalized.get("quantity") or 0)
        avg_price = Decimal(str(normalized.get("avg_price") or 0))
        ltp = Decimal(str(normalized.get("ltp") or 0))
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
                self._publish(
                    EventType.POSITION_UPDATED.value, pos
                )
                return pos
            # Update existing position
            delta = quantity - current.quantity
            updated = current.with_fill(delta, avg_price) if delta != 0 else current
            if ltp:
                updated = updated.with_ltp(ltp)
            self._positions[key] = updated
            self._publish(
                EventType.POSITION_UPDATED.value, updated
            )
            return updated

    def reset(self) -> None:
        """Clear all positions. Useful in tests."""
        with self._lock:
            self._positions.clear()

    # ── Event handlers ───────────────────────────────────────────────────────

    def on_trade(self, event: DomainEvent) -> None:
        """Handle broker trade events from the event bus.

        P5 Stability Engineering: Uses TradeFilledEvent typed wrapper
        for compile-time safety, eliminating raw dict payload access.

        Uses ``_reentrancy_guard()`` to prevent recursive handler
        invocation when the manager publishes events internally.
        """
        with self._reentrancy_guard() as guard:
            if guard.reentered:
                return
            try:
                from domain.events.types import TradeFilledEvent

                typed_event = TradeFilledEvent.from_domain_event(event)
                # P5: Idempotency - check if trade already processed (thread-safe)
                with self._lock:
                    if typed_event.trade.trade_id in self._processed_trade_id_set:
                        logger.debug(
                            "PositionManager.on_trade: skipping duplicate trade_id=%s",
                            typed_event.trade.trade_id,
                        )
                        return
                self.apply_trade(typed_event.trade)
            except ValueError as exc:
                # Invalid payload - log and skip (don't crash)
                logger.warning(
                    "PositionManager.on_trade: invalid event payload: %s",
                    exc,
                )

    def on_trade_applied(self, event: DomainEvent) -> None:
        """Apply a trade that has been verified by the OMS.

        P5 Stability Engineering: Uses TradeAppliedEvent typed wrapper
        for compile-time safety and trade_id-based idempotency.

        Uses ``_reentrancy_guard()`` to prevent recursive handler
        invocation.
        """
        with self._reentrancy_guard() as guard:
            if guard.reentered:
                return
            try:
                from domain.events.types import TradeAppliedEvent

                typed_event = TradeAppliedEvent.from_domain_event(event)
                # P5: Idempotency - track processed trade_ids (thread-safe, bounded)
                with self._lock:
                    if typed_event.trade.trade_id in self._processed_trade_id_set:
                        logger.debug(
                            "PositionManager.on_trade_applied: skipping duplicate trade_id=%s",
                            typed_event.trade.trade_id,
                        )
                        return
                    # Peek at oldest BEFORE append — deque auto-evicts on append
                    # when at capacity, so we must remove it from the set first.
                    if len(self._processed_trade_id_order) == self._processed_trade_id_order.maxlen:
                        oldest = self._processed_trade_id_order[0]
                        self._processed_trade_id_set.discard(oldest)
                    self._processed_trade_id_set.add(typed_event.trade.trade_id)
                    self._processed_trade_id_order.append(typed_event.trade.trade_id)
                self.apply_trade(typed_event.trade)
            except ValueError as exc:
                # Invalid payload - log and skip (don't crash)
                logger.warning(
                    "PositionManager.on_trade_applied: invalid event payload: %s",
                    exc,
                )

    # ── Re-entrancy guard ───────────────────────────────────────────────────

    def _reentrancy_guard(self):
        """Return a context manager for handler re-entrancy protection."""
        return _ReentrancyGuard(self._lock, self)

    # ── Helpers ─────────────────────────────────────────────────────────────

    @staticmethod
    def _key(symbol: str, exchange: str) -> str:
        return make_position_key(symbol, exchange)

    def _publish(
        self, event_type: str, position: Position | None = None, *, payload: dict | None = None
    ) -> None:
        if self._event_bus is None:
            return
        data = payload if payload is not None else {"position": position}
        symbol = position.symbol if position else payload.get("symbol", "") if payload else ""
        self._event_bus.publish(
            DomainEvent.now(
                event_type,
                data,
                symbol=symbol,
                source="PositionManager",
            )
        )
