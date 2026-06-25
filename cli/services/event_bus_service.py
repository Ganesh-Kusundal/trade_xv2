"""Event Bus Service layer for diagnostics and operation terminal."""

from __future__ import annotations

import random

from infrastructure.event_bus import EventBus


class EventBusService:
    """Monitors event bus traffic and manages metrics/counters."""

    def __init__(self):
        self.event_bus = EventBus()
        self._counters = {
            "Market Events": 0,
            "Signal Events": 0,
            "Order Events": 0,
            "Position Events": 0,
            "Risk Events": 0,
        }
        self._logs: list[str] = []

    def get_counters(self) -> dict[str, int]:
        """Fetch current event counts."""
        return dict(self._counters)

    def get_logs(self, limit: int = 50) -> list[str]:
        """Fetch rolling history of event logs."""
        return self._logs[-limit:]

    def increment(self, category: str, message: str = "") -> None:
        """Increment count for a category and append log."""
        if category in self._counters:
            self._counters[category] += 1
            if message:
                self._logs.append(message)
                if len(self._logs) > 500:
                    self._logs.pop(0)

    def simulate_event(self) -> str:
        """Simulate a random event flowing through the pipeline."""
        category = random.choice(list(self._counters.keys()))  # noqa: S311
        msgs = {
            "Market Events": [
                "LTP Update: RELIANCE NSE @ 2567.40",
                "Tick received: NIFTY IDX @ 25012.30",
                "Option Chain updated: NIFTY 18 JUN Spot=25000",
            ],
            "Signal Events": [
                "MovingAverage: BUY Signal generated for RELIANCE",
                "EMA crossover: SELL Trigger for SBIN",
                "VWAP cross: Signal generated NIFTY",
            ],
            "Order Events": [
                "Order created: DHAN-ORD-34012 Qty=10 Price=2550",
                "OMS state updated: DHAN-ORD-101 (FILLED)",
                "Order cancellation request: ZR-ORD-998 (SUCCESS)",
            ],
            "Position Events": [
                "Position updated: RELIANCE NSE (Qty=10, Realized PnL=0.00)",
                "Holding sync complete: 2 assets verified",
                "Position closed: NIFTY26JUN25000CE (PnL=+337.50)",
            ],
            "Risk Events": [
                "Risk Check: Exposure Limit check PASSED (Units=2/3)",
                "Margin check: Available margin sufficient",
                "Max daily loss check: Daily loss at 0.00 / 5000.00 (OK)",
            ],
        }
        msg = random.choice(msgs[category])  # noqa: S311
        self.increment(category, f"[{category.split()[0].upper()}] {msg}")
        return f"[{category.split()[0].upper()}] {msg}"
