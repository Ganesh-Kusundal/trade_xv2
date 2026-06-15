"""Central position management system.

Single owner for position state. All position updates go through this manager.
Protected by one ``threading.RLock`` and uses immutable ``Position`` values.
"""

from __future__ import annotations

import threading
from decimal import Decimal
from typing import Callable

from brokers.common.core.domain import Position, Trade
from brokers.common.event_bus import DomainEvent, EventBus


class PositionManager:
    """Thread-safe position book updated via trades and LTP ticks."""

    def __init__(self, event_bus: EventBus | None = None) -> None:
        self._lock = threading.RLock()
        self._positions: dict[str, Position] = {}
        self._event_bus = event_bus

    # ── Public API ──────────────────────────────────────────────────────────

    def apply_trade(self, trade: Trade) -> Position:
        """Apply a trade to the position book and return the new position."""
        key = self._key(trade.symbol, trade.exchange)
        with self._lock:
            current = self._positions.get(key, Position(symbol=trade.symbol, exchange=trade.exchange))
            delta = trade.quantity if trade.side.value == "BUY" else -trade.quantity
            updated = current.with_fill(delta, trade.price)
            self._positions[key] = updated
            self._publish("POSITION_UPDATED", updated)
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
                self._publish("POSITION_UPDATED", pos)
                return pos
            # Update existing position
            delta = quantity - current.quantity
            if delta != 0:
                updated = current.with_fill(delta, avg_price)
            else:
                updated = current
            if ltp:
                updated = updated.with_ltp(ltp)
            self._positions[key] = updated
            self._publish("POSITION_UPDATED", updated)
            return updated

    def reset(self) -> None:
        """Clear all positions. Useful in tests."""
        with self._lock:
            self._positions.clear()

    # ── Event handler ───────────────────────────────────────────────────────

    def on_trade(self, event: DomainEvent) -> None:
        """Handle broker trade events from the event bus."""
        trade = event.payload.get("trade")
        if isinstance(trade, Trade):
            self.apply_trade(trade)

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
