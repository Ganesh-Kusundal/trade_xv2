"""Event Bus Service layer for diagnostics and operation terminal.

Phase 3: this service is now a thin read-only mirror over the canonical
OMS :class:`EventBus` (built inside :class:`TradingContext`). The
previous implementation built a second, separate ``EventBus`` instance
and exposed ``simulate_event()`` which fabricated fake events. That was
a **silent safety bug**: an operator running ``tradex events`` saw
fabricated activity while the real OMS events flowed through a
different bus that was never wired to the CLI display. This module
now subscribes to the canonical bus and surfaces real events only.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from infrastructure.event_bus import EventBus


class EventBusService:
    """Read-only mirror over the canonical OMS EventBus.

    Maintains a rolling in-memory log of recent events for the CLI
    ``events`` command. If constructed without a real bus (legacy code
    paths or unit tests that do not build a TradingContext), the
    service falls back to a private empty bus that never receives
    events; the ``events`` command will then print an explanatory
    banner rather than fabricate activity.
    """

    def __init__(self, event_bus: "EventBus | None" = None) -> None:
        self.event_bus = event_bus
        self._counters: dict[str, int] = {
            "MARKET": 0,
            "ORDER": 0,
            "POSITION": 0,
            "RISK": 0,
        }
        self._logs: list[str] = []
        self._max_logs = 500
        # Phase 3: subscribe to the canonical bus so every published
        # event is captured for operator visibility. No fabrication.
        if event_bus is not None:
            try:
                event_bus.subscribe_all(self._on_event)
            except AttributeError:
                # The bus may not expose subscribe_all in older
                # versions; degrade to no-op rather than fabricate.
                pass

    def _on_event(self, event) -> None:
        """Capture every event for the rolling log + per-category counter."""
        event_type = getattr(event, "event_type", "")
        category = self._categorise(event_type)
        self._counters[category] = self._counters.get(category, 0) + 1
        line = self._format(event)
        self._logs.append(line)
        if len(self._logs) > self._max_logs:
            self._logs.pop(0)

    @staticmethod
    def _categorise(event_type: str) -> str:
        upper = event_type.upper()
        if "TICK" in upper or "QUOTE" in upper or "DEPTH" in upper or "MARKET" in upper:
            return "MARKET"
        if "ORDER" in upper:
            return "ORDER"
        if "POSITION" in upper or "TRADE" in upper:
            return "POSITION"
        if "RISK" in upper:
            return "RISK"
        return "MARKET"

    @staticmethod
    def _format(event) -> str:
        event_type = getattr(event, "event_type", "")
        symbol = getattr(event, "symbol", "") or ""
        source = getattr(event, "source", "") or ""
        ts = getattr(event, "timestamp", None)
        ts_str = ts.isoformat() if hasattr(ts, "isoformat") else str(ts)
        payload = getattr(event, "payload", {}) or {}
        order = payload.get("order")
        trade = payload.get("trade")
        if order is not None:
            detail = (
                f"{getattr(order, 'symbol', symbol)} "
                f"{getattr(order, 'side', '')} "
                f"{getattr(order, 'quantity', '')} @ "
                f"{getattr(order, 'price', '')} "
                f"status={getattr(order, 'status', '')}"
            )
            return f"[ORDER] {ts_str} {event_type} {detail}"
        if trade is not None:
            detail = (
                f"{getattr(trade, 'symbol', symbol)} "
                f"{getattr(trade, 'side', '')} "
                f"qty={getattr(trade, 'quantity', '')} "
                f"@ {getattr(trade, 'price', '')}"
            )
            return f"[POSITION] {ts_str} {event_type} {detail}"
        return f"[{source or 'EVENT'}] {ts_str} {event_type} symbol={symbol}"

    def get_counters(self) -> dict[str, int]:
        """Return a copy of the per-category counters."""
        return dict(self._counters)

    def get_logs(self, limit: int = 50) -> list[str]:
        """Return the most recent N log lines (most recent last)."""
        return self._logs[-limit:]

    def has_real_bus(self) -> bool:
        """``True`` when this service is subscribed to a real OMS bus.

        Used by the CLI ``events`` command to print an explanatory
        banner when no TradingContext is available (legacy / unit-test
        paths). The banner replaces the previous fabricated output.
        """
        return self.event_bus is not None
